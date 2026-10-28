# Token Factory — Multi-Tenant Inference Reference Framework

**Research date:** 2026-10-27 (America/Los_Angeles). Vendor documentation and pricing pages checked via the web index on that date; no source was verified in a live logged-in browser session, so all citations are flagged `index`. Prices change frequently — re-check the pricing URLs in Sources before committing money.

**Scope as given:** one operator, rented GPU infrastructure, the GPU vendor provides a *managed* (OpenAI-compatible) inference endpoint, multiple external tenants share that endpoint (logical multi-tenancy). Deliverable: portfolio-grade reference architecture + POC buildable in <24 h of code/setup.

---

## Summary — the decisions that matter

1. **Gateway: LiteLLM (OSS) for keys/budgets/spend + a thin JWT-validation shim in front of it.** LiteLLM's virtual keys, per-key/team budgets, model allowlists and Postgres spend ledger are open-source and are the best fit in the category. **But LiteLLM's JWT/OIDC auth is an Enterprise feature** (its own docs page is headed "Enterprise feature — requires a LiteLLM Enterprise license"), so the POC must *not* plan on native LiteLLM JWT validation. A ~150-line shim (or Envoy `SecurityPolicy`) validates tenant JWTs, maps them to a tenant, and injects that tenant's LiteLLM virtual key server-side. This shim is also where `cache_salt` injection, payload caps and audit stamping belong — things no gateway in this comparison does correctly out of the box for tenancy.
2. **POC IdP: ZITADEL Cloud Free (primary) or Auth0 Free (alternative) — both $0, both real external OIDC providers.** ZITADEL Free: unlimited users/organisations, 100 daily active users, 3 identity providers. Auth0 Free: 25,000 MAU, 1 enterprise connection, 5 organizations; custom domain needs card verification. Firebase/GCIP and Entra External ID are generous (50k MAU free) but are CIAM systems *you* operate, with federation (OIDC/SAML into them) free only to 50 MAU (Google) — they are a worse narrative fit for "Tenant B brings its own IdP" and heavier to set up.
3. **Cache isolation is a gateway responsibility, not a vendor feature you can assume.** On vLLM, per-request `cache_salt` (per-tenant, secret, ~256-bit) is mixed into the first prefix-cache block hash so only same-salt requests share blocks; vLLM explicitly warns this "is not an isolation boundary" and that a gateway must scope/overwrite client-supplied salts. On a *managed* endpoint that does not expose a salt equivalent or cache-hit metrics, cross-tenant cache isolation **cannot be demonstrated or verified** — the POC must either use an endpoint that exposes it, or run the cache demo against a vLLM upstream (see §5 caveats).
4. **Budgets are near-hard, not hard, unless you engineer for it.** LiteLLM spend is written asynchronously (batched, ~10–15 s in secondary analyses) and checked pre-request, so concurrent/in-flight requests can overshoot a cap. Mitigations: small `max_tokens` caps, RPM/TPM limits, and — for trial tier — pre-flight token estimation/reservation in the shim.
5. **POC total cost excluding GPU rental: $0–~$6.** IdP $0; one small VPS (Hetzner CX22-class, ~€4.49/mo + €0.50 IPv4) hosts LiteLLM + Postgres + shim via Docker Compose; pro-rated cost of a demo day is <$1. Everything else is open-source.

---

## Findings

### 1. Consumer Identity Modes

All four modes converge on one internal representation at the gateway — a **resolved principal**:

```
{ tenant_id, identity_mode, subject, key_id|client_id, actor?, scopes/models, budget_account }
```

Every downstream control (budget check, model allowlist, cache salt, audit row) keys off this principal, never off raw client-supplied headers. The modes differ only in how the principal is established.

#### (a) Factory-issued credentials (API keys / OAuth client-credentials)

**Flow:** Operator (or tenant admin via a portal) requests a key → gateway mints a virtual key bound to `tenant_id` + team/user → key shown **once** → tenant's service sends `Authorization: Bearer sk-...` → gateway hashes/looks up the key, loads its policy (models, budget, RPM/TPM, expiry) → forwards to upstream with the *real* vendor key, which tenants never see.

**Issuance & storage patterns:**
- Generate ≥256-bit random keys with a recognisable prefix (`sk-tf_live_…` + key-id segment). The prefix + a short non-secret key ID enables lookup; the secret part is stored **only as a hash**. For high-entropy machine keys, a fast hash (SHA-256, ideally HMAC-SHA-256 with a server-side pepper in KMS) is the standard pattern — slow password KDFs (Argon2id) are for low-entropy human passwords and would add latency to every request for no benefit against a 256-bit key. Never store plaintext; never log the key.
- Scoping: per-key `models` allowlist, `max_budget` + `budget_duration`, `rpm_limit`, `tpm_limit`, expiry (`duration`). LiteLLM implements exactly this shape: `POST /key/generate` with `models`, `max_budget`, `budget_duration`, `rpm_limit`, `tpm_limit`, `key_alias`, `team_id`, `user_id`, and documented scheduled rotation (`auto_rotate`, `rotation_interval`) — see Sources (LiteLLM analyses checked 2026-10-23/27, index).
- Rotation: issue-new → overlap window → revoke-old; one key per application/environment so revocation blast radius is one app. OAuth client-credentials variant: same policy binding, but the credential is a `client_id`/secret (or private-key JWT / mTLS) exchanged at a token endpoint for a short-lived access token — preferable when the tenant already has M2M OAuth tooling, and it gives you token expiry instead of long-lived bearer keys.
- The gateway **master key is never a tenant credential**: it can mint keys and rewrite config.

**Budgets/audit:** native — spend is attributed to key → user → team in the spend ledger; audit row carries `key_id` (hash prefix), tenant, model, tokens, cost.

**Pitfalls:** key leakage into repos/logs/client bundles (mitigate: one key per app, expiry, allowlists so a leaked key can't reach the expensive model); keys with no budget = "denial of wallet" (OWASP LLM10 unbounded consumption); shared keys destroying attribution; rotation that requires downtime because only one active key per tenant was designed in; master-key exposure.

#### (b) Federated consumer IdP (tenant's own Okta / Entra / Google via OIDC)

**Flow:** Tenant admin registers the factory as a relying party in *their* IdP (or the factory registers a client in a tenant-dedicated realm — see §2 distinction) → tenant user/service obtains an ID/access token from their IdP (auth-code+PKCE for humans, client-credentials for services) → calls gateway with the JWT → gateway validates → maps claims to `tenant_id` → policy/budget applied as in (a), usually by internally resolving to a team/virtual-key-equivalent account.

**What the gateway validates (checklist, per LiteLLM's JWT docs, index):**
- Signature against the issuer's JWKS, selected by `kid`; asymmetric algs only (RS256/384/512, PS*, ES*, EdDSA — HMAC `HS*` rejected).
- `iss` — exact string match (trailing slash and http/https matter); `aud` — must contain the gateway's audience; `exp`/`nbf`/`iat` with small clock-skew leeway (≤60 s recommended).
- Then claim mapping: e.g. LiteLLM per-issuer config (`litellm_jwtauth.issuers[]`) supports per-issuer `jwks_url`, `audience`, and claim fields `team_id_jwt_field`, `user_id_jwt_field` (`sub`), `org_id_jwt_field`, `user_email_jwt_field`, with dot-notation for nested claims (e.g. Keycloak `resource_access.<client>.roles`). Roles/scopes map to model allowlists (LiteLLM `role_permissions`: role → models, with `enforce_rbac`).
- JWKS caching/rotation behaviour matters: LiteLLM caches key sets for `public_key_ttl` (default 600 s); a `kid` miss does *not* trigger refetch inside the TTL, so a just-rotated IdP key is rejected until expiry; stale-copy fallback defaults to 600+3600 s unless set to fail closed. Multi-provider warning from the same docs: the shared `JWT_PUBLIC_KEY_URL` list selects keys by `kid` alone and can only verify a single shared `iss`/`aud` — use per-issuer config so `iss` is actually verified per provider, and leave the global path unset so unlisted issuers are rejected.

**Tenant mapping:** never trust a client-supplied tenant header. Map `(iss, tenant-claim)` → `tenant_id` from an operator-controlled registry: each federated tenant has exactly one (or an allowlist of) issuer URL(s) + audience + claim name. A valid token from Tenant B's IdP must be unable to assert Tenant A's ID.

**Budgets/audit:** the resolved tenant maps to a LiteLLM team (created out-of-band; LiteLLM does not auto-create teams from OIDC claims — claim values with no matching team are skipped, per its SSO docs). Audit row: `iss`, `sub`, tenant, identity_mode=`federated`.

**Pitfalls:** accepting ID tokens instead of access tokens (wrong `aud`); not verifying `iss` when multiple IdPs are configured (any tenant's IdP — or any app on a shared IdP like Google — can then impersonate); algorithm confusion (`none`/`HS256` with public key); JWKS rotation outages vs fail-open stale keys; claim-name collisions across IdPs (`sub` is only unique per issuer); tenant onboarding friction (redirect URIs, custom domains, IdP admin availability) — this, not code, is the schedule risk; group-claim overage (Entra/Google truncate large group lists).

#### (c) Delegated / agent mode (agent acting for an end user)

**Flow (RFC 8693 token exchange, single trust domain):** User authenticates to their IdP → agent obtains the user's token → agent calls the IdP/AS token endpoint with `grant_type=urn:ietf:params:oauth:grant-type:token-exchange`, `subject_token=<user token>`, optionally `actor_token=<agent's own token>`, requested audience/scope (attenuated) → AS returns a short-lived token whose `sub` = user, with an **`act` claim** naming the agent (nested `act` for delegation chains) → agent presents that token to the gateway → gateway validates as in (b) **plus** extracts `act`.

**Cross-domain variant — ID-JAG / Cross-App Access:** When the agent and the resource sit in different trust domains, the pattern standardised as the Identity Assertion Authorization Grant (IETF draft `draft-ietf-oauth-identity-assertion-authz-grant`, rev. 04 dated 2026-05-21; Okta's product name: Cross App Access, XAA; adopted by MCP as Enterprise-Managed Authorization, GA June 2026) chains two exchanges: (1) RFC 8693 exchange at the user's IdP with `requested_token_type=…:id-jag` producing an ID-JAG (Okta sample: ~300 s lifetime), then (2) RFC 7523 JWT-bearer grant at the *resource's* authorization server, exchanging the ID-JAG for a resource-scoped access token whose `aud` is the resource. Consent/policy lives at the IdP (admin pre-authorises which apps/agents may reach which resources) instead of per-app consent screens.

**What the gateway validates/authorises:** both identities independently — user (`sub`, tenant from user's `iss`) **and** agent (`act.sub` / agent client ID). Authorisation = intersection: agent's allowed models ∩ user's allowed models ∩ tenant policy. Scopes must only ever narrow across the exchange (attenuation); reject exchanges that widen scope, lack `act` when an agent header is present, or present a raw user session token forwarded by an agent ("token passthrough" — the anti-pattern this mode exists to replace).

**Budgets/audit:** charge the **tenant/user budget account**, but rate-limit and anomaly-alert on the **agent** identity as well; audit rows carry both `sub` (user) and `act` (agent) plus delegation depth. Either identity must be independently revocable: killing the agent's registration must not require resetting the user's credentials and vice versa.

**Pitfalls:** confused-deputy (agent tricked into using its delegation for another user — bind tokens to the agent's key/thumbprint where possible, e.g. DPoP/mTLS sender-constraining); recursive/unbounded delegation chains (cap `act` nesting depth, typically 1); long-lived delegated tokens (minutes, not hours); audit logs that record only the user, making agent abuse unattributable (this is the most common real-world failure); assuming ID-JAG support — it is a 2026 draft with Okta/Auth0-led implementations, not something every tenant IdP offers yet, so the factory should implement RFC 8693 `act`-claim support first and treat ID-JAG as the cross-domain upgrade path.

#### (d) Trial tier (email-verified or anonymous, hard-capped)

**Flow:** Sign-up with email verification (magic link / OTP) or anonymous session → factory mints a trial-scoped credential (short-lived JWT or a factory key with trial policy) → gateway enforces trial policy → on exhaustion, hard 402/429 with an upgrade path, no silent overage.

**Controls that make it safe:** tiny hard budget (e.g. $0.50–$2 total, not monthly-resetting by default), 1 model (cheapest), low RPM/TPM, small `max_tokens` per request and max context, short credential lifetime (hours–days), one trial per verified email **and** per payment-fingerprint/IP/ASN heuristics, CAPTCHA/bot check at sign-up, no streaming abuse surface (or capped stream duration), content logging minimised (trial traffic is the most adversarial).

**Budgets/audit:** trial budget account is separate from paid tenant accounts so trial burn can never consume a paying tenant's budget; audit still stamps every call (trial is where abuse telemetry comes from).

**Pitfalls:** Sybil farming (disposable emails → require verification + velocity limits; anonymous-only trials are effectively an open proxy to the internet and will be found by scanners within hours); trial keys being used as a free inference API by scripts (per-request token caps + total cap, not just RPM); cost of email/SMS verification itself (SMS OTP is the classic toll-fraud vector — Google charges per SMS by region, $0.01 US to $0.46 top-tier, first 10/day free on GCIP — prefer email magic links for the POC); forgetting that "hard cap" must include in-flight concurrency (see Summary point 4).

**Mode comparison:**

| | (a) Factory keys | (b) Federated IdP | (c) Delegated/agent | (d) Trial |
|---|---|---|---|---|
| Who vouches | Factory | Tenant's IdP | User's IdP + agent registration | Factory (email proof) |
| Credential | Virtual key / client creds | Tenant-IdP JWT | Exchanged JWT w/ `act` (or ID-JAG→access token) | Short-lived trial key/JWT |
| Gateway validates | Key hash + policy | Sig/JWKS, `iss`, `aud`, `exp`, claims | (b) + `act`, scope attenuation | Key/JWT + trial policy |
| Budget attaches to | Key/team | Mapped team | User/tenant (limit also per agent) | Trial account |
| Audit identity | `key_id`, tenant | `iss`+`sub`, tenant | `sub` **and** `act`, tenant | Trial user ID, tenant=`trial` |
| Biggest pitfall | Leakage, no-budget keys | Unverified `iss` across IdPs | Token passthrough; user-only audit | Sybil / open-proxy abuse |

### 2. Free or Low-Cost IdP for the Federated Path

**Framing distinction the POC depends on:** options below are IdPs *the operator runs for a demo tenant* (Auth0 tenant, ZITADEL organisation, GCIP project, Entra external tenant, self-hosted Keycloak) — all can act as the OIDC provider whose JWTs the gateway validates. A tenant's *real pre-existing* corporate IdP (their Okta/Entra/Google Workspace) is the production story for mode (b); its free tiers are trial/integrator-grade only (Okta: no permanent free workforce plan).

| Option | Can be OIDC provider for demo tenant? | Free tier (Oct 2026) | Overage / next step | Gotchas |
|---|---|---|---|---|
| **ZITADEL Cloud** | Yes — full OIDC/OAuth2, organisations = tenants, custom claims via Actions | **$0: unlimited stored users & organisations, 100 daily active users, 3 identity providers, all security features** (vendor pricing page, index-fetched) | Pro $100/mo incl. 25,000 DAU/mo + custom domain | DAU (not MAU) metric; custom domain is a Pro feature — POC uses the `*.zitadel.cloud` domain; self-host OSS (Apache-2.0) is the escape hatch |
| **Auth0 (Okta CIC) Free** | Yes — the most familiar demo IdP; create an API (audience) + application, users sign in, gateway validates RS256 JWTs | **$0 up to 25,000 MAU; 5 Organizations, 1 Enterprise Connection, Self-Service SSO + SCIM, unlimited social connections** (Auth0 pricing page as read 2026-10-26 by multiple trackers, index) | B2C Essentials $35/mo, B2B Essentials $150/mo (both at 500 MAU) | **Custom domain on Free requires credit-card verification** (Auth0's own blog); MFA is paid-tier; free-tier entitlements changed more than once in 2026 — re-verify at build time; enterprise connections beyond 1 require B2B plans |
| **Google Identity Platform / Firebase Auth** | Yes, with a caveat: it is a CIAM you operate. Its own tokens (Tier-1: email/social/anonymous) are OIDC JWTs a gateway can validate via Google's JWKS (`securetoken.google.com/<project>`). Using it to *federate a tenant's external OIDC/SAML IdP into it* is Tier-2 | **Tier-1: 50,000 MAU free**, then $0.0055/MAU (50–100k) tiering down to $0.0025. **Tier-2 (OIDC/SAML): 50 MAU free, then $0.015/MAU** (Google Cloud pricing page, index-fetched; Firebase pricing page agrees: "50K MAUs no-cost; SAML/OIDC 50 MAUs no-cost") | Blaze (pay-as-you-go) plan required for Identity Platform features — i.e. a billing account/card on file even at $0 usage | Phone/SMS billed per message by region; Firebase Auth ≠ a general-purpose enterprise IdP (no first-class org/tenant model for B2B federation); US-only auth processing noted by trackers; best if Tenant B is really "users in a Google project", weakest narrative for "tenant's own IdP" |
| **Microsoft Entra External ID** | Yes — external (CIAM) tenant issues OIDC tokens; also, a plain **Entra ID Free workforce tenant** (included with Azure/M365) can register an app and act as OIDC provider for a handful of demo users | **External ID core: first 50,000 MAU free** (Microsoft Learn FAQ, index); add-ons have **no** free tier. Entra ID Free: $0/tenant; P1 $7, P2 $10 per user/mo (annual; raised 2026-07-01) | External ID above 50k MAU: ~$0.03/MAU (Basic) per licensing guides citing Microsoft's pricing page; governance add-on $0.75/MAU | Requires an Azure subscription linked for MAU billing to unlock add-ons; portal/tenant-type confusion is notorious (workforce vs external tenant; Azure AD B2C is **not sold to new customers since 2025-05-01**, supported to ≥2030); custom domain uses `ciamlogin.com` default; heaviest setup of the free options — budget hours, not minutes |
| **Okta (Workforce / Customer Identity)** | Technically yes, commercially no for this POC | **No permanent free plan.** 30-day trial; **Integrator Free Plan: up to 10 active users, non-production only** (Okta developer terms, index) | Workforce Starter $6/user/mo with **$1,500/yr minimum**; Customer Identity Enterprise base ~$3,000/mo | Integrator orgs are for building integrations, deactivate after inactivity (~90 days per terms/trackers); use Okta as the *story* for mode (b)/(c) (it leads ID-JAG/XAA) but not as the POC's free IdP unless the 10-user integrator org suffices |
| **Keycloak (self-hosted)** | Yes — the reference OSS IdP: realms = tenants, full OIDC/OAuth2/SAML, custom claim mappers | **$0 licence (Apache-2.0), unlimited users**; cost = hosting only | Managed Keycloak exists from ~$29/mo (third parties); Red Hat build/support is commercial | You own upgrades, CVE patching, backups, HA. On the POC VPS (shared with the gateway) marginal cost $0; standalone small VPS ~€4–5/mo (below). Realm/client/claim-mapper setup is the fiddliest of the OSS options (~1–2 h first time) |
| **ZITADEL (self-hosted)** | Yes — same product as cloud free tier, single binary + Postgres/CockroachDB | **$0 (Apache-2.0), unlimited users** | Cloud Pro $100/mo if you stop self-hosting | Lighter to run than Keycloak; smaller community; needs its own domain/TLS for a realistic demo |
| **SuperTokens (self-hosted / cloud)** | **Partial / weakest fit.** It is an app-embedded auth/session layer (core Apache-2.0), not a standalone general-purpose OIDC provider for arbitrary relying parties in the way Keycloak/ZITADEL are; enterprise SSO/multi-tenancy are add-ons | Self-hosted core **free, no user limit**; managed cloud **free <5,000 MAU, then $0.02/MAU** (SuperTokens' own comparison, Sep 2026, index) | MFA add-on $0.01/MAU with $100/mo minimum; multi-tenancy/M2M via paid/custom plans | Choose it to add login *inside your own app*, not as Tenant B's external IdP; verifying a standalone OIDC-provider flow from its docs for this exact use was not established (see Could not verify) |

**Self-hosting cost basis:** a Hetzner CX22-class VPS (2 vCPU / 4 GB) is ~€4.49/mo after the April 2026 price adjustment (+€0.50/mo IPv4), ≈ $5–6 — enough for Keycloak *or* ZITADEL + Postgres for a demo, and in the POC design (§5) it is the *same* VPS that runs the gateway, so incremental IdP cost is $0 if cloud ZITADEL/Auth0 is used, or $0 extra if Keycloak/ZITADEL is added to the box (at the price of setup time). DigitalOcean equivalent (4 GB) is $24/mo — avoid for the POC.

**Verdict for §5:** ZITADEL Cloud Free (fastest real external OIDC, organisations map to tenants, no card mentioned for the free tier) → Auth0 Free as the recognisable-name alternative → Keycloak-on-the-same-VPS as the zero-vendor fallback. All three are $0, satisfying the "free or <$5 total" IdP constraint with margin.

### 3. Gateway and Multi-Tenancy on Shared Endpoints

| Gateway | JWT/OIDC validation | Per-tenant budgets & rate limits | Spend ledger / audit | Model allowlist per tenant | Deployment |
|---|---|---|---|---|---|
| **LiteLLM (OSS)** | **Enterprise-only** for JWT auth (docs-headed; per-issuer JWKS, `iss`/`aud`, claim→team/user mapping, role→model RBAC). OSS gets virtual-key auth + Admin-UI SSO. POC workaround: shim/Envoy in front (below) | **Yes, best-in-class OSS:** per key/user/team/tag `max_budget`+duration, RPM/TPM; blocked when exceeded | **Yes:** Postgres `SpendLogs` per key/user/team/model/tag; callbacks to Langfuse/Datadog/OTel. **Audit logs proper are Enterprise** | **Yes:** per-key `models`, team model access, role permissions | Self-host Docker; needs Postgres (Redis for multi-instance/rate limits) |
| **Portkey** | Hosted: virtual keys; SSO Enterprise-only. **OSS gateway: no JWT validation and no virtual keys at all** — clients send the provider key + config in headers (verified in an Oct 2026 self-host test, index) | Hosted: per-virtual-key/workspace budgets & rate limits with hard enforcement. OSS: per-provider rate limits only | Hosted: log-metered (Developer free 10k logs/mo, 3-day retention; Production $49/mo, 100k logs, +$9/100k); audit logs paid/Enterprise | Hosted: yes via virtual keys/configs. OSS: no | Hosted SaaS, self-host OSS (Node), VPC Enterprise. **Ownership change: acquired by Palo Alto Networks (closed 2026-05-29), now Prisma AIRS AI Gateway — roadmap/pricing risk to flag** |
| **Kong AI Gateway** | OSS: `jwt`, `key-auth`, `oauth2` plugins ship free, but **`openid-connect` is Enterprise-only** (OSS image plugin audit, index); raw JWT plugin validates signatures but claim→tenant policy is DIY/Lua | OSS: request rate-limiting; **token-based `ai-rate-limiting-advanced` and AI spend controls are Enterprise**. Consumers/consumer-groups are the tenancy primitive | Via logging plugins to SIEM/S3; audit logging Enterprise/Konnect | Via ACL + AI-proxy plugin config per route/consumer; laborious | Self-host (NGINX/OpenResty + Postgres or DB-less) or Konnect SaaS. Enterprise historically ~$40k+/yr — wrong scale for this POC |
| **Cloudflare AI Gateway** | **No native validation of arbitrary tenant JWTs.** Identity only via Cloudflare Access in front (Access JWT → reserved `cf.user_id` metadata). Without Access, per-user dimensions are **client-supplied custom metadata (max 5 entries) and are spoofable** — its own spend-limits docs say exactly this distinction | **Spend limits (open beta, all plans):** dollar budgets scoped by model/provider/custom-metadata dimensions, daily/weekly/monthly windows, block-by-default. Rate limiting per gateway. No per-tenant keys | Logs/analytics per gateway; log storage follows Workers Logs pricing for accounts created on/after 2026-09-24 (legacy: 100k logs free). Logpush paid | Not per-tenant natively; Dynamic Routing can branch on metadata/headers — DIY policy | Fully managed edge; core features free on all plans; Unified Billing adds 5% on credit purchases (BYOK = no gateway fee) |
| **Envoy AI Gateway (OSS)** | **Yes, natively:** `SecurityPolicy` JWT — remote JWKS, `issuer`, `audiences`, `claimToHeaders` (strips client-forged headers, injects verified claims upstream) | Token-usage-based global rate limiting: `BackendTrafficPolicy` cost charged from response metadata (`llm_total_token`/input/output) per distinct header (e.g. `x-tenant-id`) — real per-tenant token budgets per window. **No dollar budget ledger** | **No built-in ledger/audit DB** — Prometheus metrics + OTel traces; you build the ledger | Per-route/`AIGatewayRoute` model routing; allowlist = route config per tenant route — DIY | Kubernetes only (Gateway API CRDs + Envoy + external rate-limit service/Redis). Heaviest ops of the list; no K8s in the POC = disqualifying for 24 h |
| **Bifrost (Maxim, OSS)** | Virtual keys natively; **SSO/OIDC is Enterprise** (same pattern as LiteLLM) | **Yes:** hierarchical budgets (customer → team → virtual key → provider config), token/$ rate limits, budget-out returns **402** | Built-in logging (SQLite default/Postgres), OTel/Prometheus export; **audit logs Enterprise** | Yes: per-virtual-key model/provider permissions | Single Go binary/container, fastest setup after LiteLLM; smaller provider catalogue/community than LiteLLM |

*Other credible options noted, not deep-dived:* TrueFoundry, Helicone AI Gateway (beta), Vercel AI Gateway (managed, per-team/project/key budgets, no self-host), OpenRouter (marketplace, not a tenancy gateway for your own endpoint).

**Reading of the table:** every OSS gateway paywalls *either* JWT/OIDC *or* audit/SSO behind Enterprise. That is the category's business model in 2026, and it dictates the reference design: **OSS gateway for money controls (keys, budgets, spend) + a small owned auth layer for identity (JWT validation, tenant mapping, delegation) + your own append-only audit table.** Buying Enterprise to avoid ~200 lines of shim is not portfolio-scale rational.

#### Isolation specifics on shared inference

- **Prefix-cache isolation (vLLM):** automatic prefix caching reuses KV blocks for shared prompt prefixes. That is a *timing side channel*: a cache hit's faster time-to-first-token reveals that a guessed prefix was recently used by someone (vLLM security docs cite CVE-2025-46570; research signal ROC AUC 0.99 at just 8 tokens). Mitigation: per-request **`cache_salt`** — mixed into the hash of the **first block only** (which chains: all subsequent blocks hash from their parent, so the whole prefix is effectively salted) — such that only same-salt requests can share blocks. vLLM's API docs specify the salt should be **random, secret, unpredictable, ~256-bit** (43-char base64).
- **Rules the gateway must enforce:** (1) salt is derived from the *authenticated tenant* (e.g. stored per-tenant secret, or `HMAC(server_secret, tenant_id)`), **never accepted from client input** — the gateway strips any client `cache_salt` and overwrites it; (2) same treatment for multimodal `uuid` values and `kv_transfer_params` (vLLM docs: shared UUIDs across tenants cause cross-tenant media-cache sharing — integrity *and* confidentiality failures — and `kv_transfer_params` should be stripped/validated at the proxy); (3) salts rotate on tenant off-boarding/key compromise, accepting a cold cache per tenant.
- **Honest limits (from vLLM's own docs):** "vLLM does not provide isolation between tenants that share the same server process… `cache_salt` reduces specific cross-tenant risks, but **is not an isolation boundary**." Tenants still share scheduling/GPU — a noisy neighbour can degrade latency, and timing channels beyond the prefix cache are not closed. True isolation = dedicated instance per tenant (deferred in §4, priced as the enterprise tier).
- **Managed endpoints:** if the GPU vendor's managed endpoint is vLLM-based *and* passes through `cache_salt` *and* exposes cache-hit/TTFT metrics, the above applies. If it is a proprietary stack with automatic prompt caching scoped per vendor-account (typical), then **all your tenants sit inside one vendor account and you have no salt to set** — mitigations are limited to asking the vendor, disabling caching if an option exists, or accepting + documenting the residual risk. This must be a vendor-selection checklist item, not an afterthought.
- **Response caching at the gateway is a separate, worse trap:** Cloudflare/LiteLLM/Portkey response caches keyed on prompt content will *serve one tenant's answer to another*. Rule: disable gateway response caching on multi-tenant routes, or include tenant + identity + model version in the cache key. Semantic caching across tenants is prohibited outright.
- **Request/payload validation at the gateway (before upstream):** JSON schema + size caps; allowlisted parameters only; cap `max_tokens`, `n` (vLLM's own `VLLM_MAX_N_SEQUENCES` default is 16384 — set 64–128 for public traffic), context length, image/URL inputs (SSRF: allowlist media domains, block metadata IPs — vLLM ships `--allowed-media-domains` for its side); strip upstream-identity fields (`cache_salt`, `kv_transfer_params`, `mm_processor_kwargs`, tool/server params); per-tenant concurrency cap so one tenant cannot fill the shared batch.
- **Upstream endpoint hardening (if it is raw vLLM anywhere in the chain):** its `--api-key` protects only `/v1`, `/v2`, `/inference`, `/cohere` prefixes; `/invocations`, `/pause`, `/abort_requests`, `/collective_rpc` (dev mode), `/metrics`, `/reset_prefix_cache` are unauthenticated. The endpoint must be network-private, reachable only from the gateway, with the gateway allowlisting paths. For a managed vendor endpoint the equivalent is: vendor API key held only by the gateway, IP-allowlist/private networking if offered, and no direct tenant route to the vendor URL.
- **Per-tenant audit records:** one append-only row per request, written by the gateway/shim (not inferred later from vendor bills): `request_id, timestamp, tenant_id, identity_mode, subject (iss+sub or key_id), actor (act claim) if any, model requested/served, prompt_tokens, completion_tokens, cached_tokens, cost, cache_salt_id (not the salt), latency/TTFT, status, policy decisions (budget before/after)`. Store prompt/response *bodies* separately, encrypted, short-retention, or not at all — metadata audit ≠ content logging.

### 4. Reference Architecture

```
                        ┌─────────────── Tenant IdPs (mode b/c) ───────────────┐
                        │  Tenant Okta / Entra / Google · Demo: ZITADEL/Auth0  │
                        └──────────────────────┬───────────────────────────────┘
                                               │ OIDC discovery + JWKS (cached)
 Tenants                                       ▼
 ┌─────────┐   Bearer key (a,d)      ┌──────────────────┐
 │Tenant A │────────────────────────▶│  EDGE / AUTH SHIM │  TLS, WAF-lite, body caps
 │Tenant B │── Bearer JWT (b) ──────▶│  - key-hash lookup│
 │Agent    │── Exchanged JWT (c) ───▶│  - JWT validate   │
 │Trial    │── Trial key (d) ───────▶│  - tenant resolve │
 └─────────┘                         │  - audit stamp    │
                                     └────────┬─────────┘
                                              │ internal: tenant virtual key +
                                              │ cache_salt + capped params
                                     ┌────────▼─────────┐      ┌────────────────┐
                                     │  LiteLLM (OSS)   │─────▶│ Postgres       │
                                     │  teams, virtual  │      │ keys, teams,   │
                                     │  keys, budgets,  │      │ SpendLogs,     │
                                     │  model allowlist │      │ audit table    │
                                     └────────┬─────────┘      └────────────────┘
                                              │ vendor key (only here)
                                     ┌────────▼─────────┐      ┌────────────────┐
                                     │ Managed inference │      │ Secrets: env/  │
                                     │ endpoint (rented  │      │ KMS (master key,│
                                     │ GPU vendor)       │      │ vendor key,    │
                                     └───────────────────┘      │ salt secrets)  │
                                                                  └────────────────┘
```

**Components:**
- **Edge/auth shim** (owned code, ~150–300 LOC FastAPI or an Envoy/Caddy ext-auth config): terminates TLS (via Caddy/Traefik for free certs), resolves the principal for all four modes, strips/overwrites client-supplied tenancy fields, injects `cache_salt`, caps payload params, writes the audit row, and forwards to LiteLLM with the tenant's virtual key held server-side for JWT modes (for key modes the client's key *is* the LiteLLM key and the shim can be a pass-through validator/cache-salter — in the POC the shim fronts both paths uniformly for audit consistency).
- **Gateway (LiteLLM OSS + Postgres, Redis optional):** model catalogue (logical names → vendor deployment), virtual keys, teams, budgets, RPM/TPM, spend ledger, provider fallback (defer beyond one fallback rule).
- **Identity layer:** tenant registry table (`tenant_id, mode, issuer(s), audience, claim map, IdP metadata, status`) + JWKS cache with the §1(b) rotation policy; factory key service = LiteLLM `/key/generate` wrapped by an operator CLI (no portal in POC).
- **Key/secret management:** POC — environment secrets on the VPS (file perms 600, never in git) for `LITELLM_MASTER_KEY`, vendor key, salt secret, DB password. Production note: cloud KMS/Secrets Manager or Vault, with the LiteLLM DB-encryption (salt) key stored *separately* from the DB backup (a restore needs DB + config + decryption key together, but they must not be stored together).
- **Budget ledger:** LiteLLM SpendLogs is the system of record; shim adds a pre-flight check for trial/agent modes and a nightly reconciliation against the vendor's usage/bill export (vendor bills are delayed/coarse — never the enforcement source).
- **Cache isolation:** per-tenant salt secret; gateway injection as in §3; gateway response cache **off**.
- **Audit log:** Postgres append-only table (POC) → export to object storage/SIEM later; hash-chaining rows is a cheap tamper-evidence upgrade, defer if time is short.
- **Managed inference endpoint:** single upstream in POC; vendor key only in gateway config; endpoint not publicly routable from tenants.

**Request flow per mode:** (a) key → shim hash-lookup/principal → LiteLLM enforces key's own budget/allowlist → upstream. (b) JWT → shim JWKS-validates, `(iss, claim)`→tenant → shim presents tenant's server-side virtual key to LiteLLM → team budget applies. (c) exchanged JWT → shim validates + requires `act`, checks agent registry + scope attenuation → same as (b) with dual-identity audit. (d) trial key → shim checks trial ledger/reservation → LiteLLM trial team with $ cap, cheapest model only.

**Build vs buy vs defer (portfolio/POC scale):**

| Build (own it, it's the portfolio value) | Buy/use off-the-shelf | Defer (name it explicitly) |
|---|---|---|
| Auth shim (4-mode principal resolution), tenant registry, cache-salt injection, payload caps, audit table + demos | LiteLLM OSS (keys/budgets/spend), ZITADEL/Auth0 free IdP, Caddy TLS, Docker Compose, Postgres | Real billing/payments & invoicing (budgets are *caps*, not billing), SLOs/multi-region, dedicated per-tenant endpoints (the true-isolation tier), SCIM provisioning, self-service tenant portal, semantic guardrails/PII suite, multi-vendor routing sophistication |

**Reviewer security checklist:** ☐ keys hashed (HMAC-SHA-256+pepper or gateway-native), shown once, never logged, master key separated ☐ vendor key exists only in gateway secrets ☐ JWKS: per-issuer `iss`+`aud` enforced, HS* rejected, rotation tested (kid-miss behaviour understood), fail-closed vs stale policy chosen deliberately ☐ clock skew ≤60 s, `exp`/`nbf` checked, short token lifetimes ☐ replay: JWTs are bearer — mitigate with short expiry + `jti` denylist only for high-value ops; API-key replay bounded by budget/allowlist; consider DPoP/mTLS for agent mode ☐ `cache_salt` overwritten server-side, secret per tenant, cache-isolation test in CI (§5) ☐ client-supplied `kv_transfer_params`/UUIDs/extra params stripped ☐ gateway response cache off or tenant-keyed ☐ upstream endpoint not directly reachable; non-`/v1` paths blocked ☐ budget hard-stop tested under concurrency; in-flight overshoot bounded by `max_tokens` caps ☐ audit row for *every* request incl. rejections, with identity mode + actor ☐ prompt bodies not in audit logs ☐ trial anti-Sybil controls ☐ TLS everywhere, admin UI (`/ui`) not public or behind auth+IP allowlist ☐ DB backed up, restore rehearsed, secrets not in the backup.

### 5. POC Design (under 24 hours)

**Goal demos:** ① Tenant A (factory key) and Tenant B (external OIDC) call the *same* model on the *same* shared endpoint through one gateway; ② a per-tenant budget cap fires; ③ cache isolation between tenants; ④ audit log attributes every call to tenant + identity mode.

**Components (all off-the-shelf except the shim):**

| Piece | Choice | Off-the-shelf / custom |
|---|---|---|
| VPS | Hetzner CX22-class (2 vCPU/4 GB), Docker Compose | Off-the-shelf |
| Reverse proxy/TLS | Caddy (automatic Let's Encrypt) on a cheap/free subdomain | Off-the-shelf |
| Gateway | LiteLLM OSS + Postgres (Compose services), one logical model → managed endpoint (OpenAI-compatible `api_base` + vendor key), **set an internal per-token price for the model in LiteLLM config if the vendor is flat-rate GPU rental — otherwise budgets denominated in $ will read $0 and the budget demo will not fire** | Off-the-shelf + config |
| Tenant B IdP | ZITADEL Cloud Free: one organisation = Tenant B, one user, one project/application (audience), a claim (via Action/custom claim) carrying e.g. `tenant_id=tenant-b` or use `iss`→tenant mapping in the shim only. Fallback: Auth0 Free (create API with audience, one user) | Off-the-shelf |
| Auth shim | FastAPI (~150–250 LOC): PyJWT + `PyJWKClient` (JWKS cache), checks `iss`/`aud`/`exp`, maps to Tenant B, forwards to LiteLLM with Tenant B's virtual key + `cache_salt=HMAC(secret,"tenant-b")`; for Tenant A path, validates/forwards the LiteLLM key and injects Tenant A's salt; writes audit rows (SQLite/Postgres table) | **Custom — the only real code** |
| Tenants in LiteLLM | Team A + virtual key A (`max_budget: 0.05` for the demo, cheapest model only, RPM cap); Team B + virtual key B (held by shim only) | Config/API calls |
| Cache demo upstream | The managed endpoint **if** it passes `cache_salt` and exposes TTFT or cache metrics; otherwise a tiny vLLM on the rented GPU (or any vLLM you control) as the demo upstream — see caveat | Config |

**Setup steps & time budget (~16–20 h total):**
1. (1 h) VPS + Docker + Caddy + domain/TLS. 2. (2 h) LiteLLM+Postgres up, model wired to managed endpoint, smoke test with master key. 3. (1 h) Teams/keys A & B with budgets/allowlists; verify A's key, spend log rows. 4. (2 h) ZITADEL tenant: org, user, app, token with claim; decode and record real `iss`/`aud`/`kid`. 5. (4–5 h) Shim: JWT validation, tenant mapping, key injection, salt injection, param caps, audit writes; negative tests (wrong aud, expired, Tenant-A salt forgery attempt). 6. (2 h) Budget demo: set A budget to a few cents, loop calls until LiteLLM rejects with budget-exceeded; repeat for B via shim. 7. (2–3 h) Cache demo (below). 8. (2 h) Audit demo + README/screenshots: query audit table by tenant/mode; export a sample. 9. (2 h buffer) Pitfalls, below.

**Cache-isolation demo protocol:** use a long shared prefix (≥512 tokens of tenant-"secret" text, ≫ vLLM's 16-token block). Sequence: A sends prefix+question → A repeats (expect cache hit: drop in TTFT / `cached_tokens`/prefix-cache-hit metric) → B sends *identical* prefix (different salt → expect **miss**: TTFT ≈ A's first call, no hit metric) → B repeats (B now hits its *own* salted cache). Present TTFT table + metrics. **Caveats, stated in the deliverable:** (i) with different salts there is no cross-tenant *reuse*, so there is also nothing to leak via reuse — the demo shows absence of benefit + absence of the timing signal; run one control pass with salts disabled (test config only) to show B *would* get A's hit — that contrast is the actual evidence; (ii) TTFT is noisy on shared/managed infra — use medians of 5+ runs; (iii) if the managed endpoint hides cache metrics and ignores `cache_salt`, this demo is **not possible against it** — say so and run it against the vLLM upstream; do not fake it with gateway response caching.

**Audit demo:** single SQL query / log view showing for each call: tenant, mode (`factory_key` vs `oidc`), subject/key-id, model, tokens, cost, budget-after, salt-id, TTFT, status — including the rejected over-budget and bad-token calls.

**Expected total cost (excluding GPU rental):** IdP $0 (ZITADEL/Auth0 free) · VPS ~€4.49 + €0.50 IPv4 per month (≈$5–6; demo-day pro-rata <$1) · domain $0 (existing/free subdomain) to ~$12/yr if bought · LiteLLM/Postgres/Caddy $0 · **Total: $0–6 for the POC month, comfortably inside the <$5 IdP constraint (IdP itself $0).**

**Known pitfalls that eat time:** ① LiteLLM JWT auth being Enterprise — discovering this late (hence shim-first design); ② LiteLLM budgets reading $0 for self-hosted/flat-rate endpoints until you set model prices in config; ③ `iss` trailing-slash / audience mismatch (Auth0 audience = API identifier, ZITADEL audience/project quirks) — debug by decoding a real token first; ④ JWKS cache TTL making rotated/test keys look "randomly" rejected; ⑤ budget overshoot from async spend writes making the cap-fire demo look soft — use sequential calls for the demo; ⑥ Caddy/TLS + redirect-URI mismatches in the IdP console; ⑦ managed endpoint not being truly OpenAI-compatible (extra required headers/params) or silently ignoring `cache_salt`; ⑧ Postgres persistence in Compose (named volumes) lost on `down -v`; ⑨ time sync on the VPS (clock skew → all JWTs "expired"); ⑩ ZITADEL DAU counting admins/test users — irrelevant at POC scale but surprises people reading the dashboard.

---

## Could not verify

- **LiteLLM's internal key-storage hashing details** (exact hash/HMAC construction for virtual keys in current version) were not established from primary docs in this pass; the §1(a) hashing guidance is the standard pattern + gateway behaviour, not a claim about LiteLLM internals.
- **SuperTokens as a standalone OIDC provider** for an arbitrary gateway relying party: sources establish it as app-embedded auth with OIDC *consumption* and paid multi-tenancy/SSO add-ons; a primary-source confirmation of it issuing OIDC tokens to arbitrary RPs for this exact pattern was not found — hence "weakest fit" rather than a hard no.
- **Entra External ID overage rate ($0.03/MAU)** comes from licensing guides citing Microsoft's pricing page (the Microsoft page itself was reached only via Learn FAQ/Q&A in this pass, which confirms the 50,000-MAU free core but not the overage number in the fetched text).
- **The specific managed GPU vendor was not named in the mission**, so `cache_salt` pass-through, cache metrics, per-token vs flat-rate pricing, and IP-allowlisting for *the* endpoint could not be verified — §3/§5 treat these as vendor-selection checks. Likewise no tenant count, model, or region was specified.
- All pricing/limits are October 2026 index snapshots; Auth0 in particular changed free-tier entitlements multiple times in 2026.

## Sources

All read 2026-10-27 via web index (`index`); vendor pages are primary unless noted.

- LiteLLM JWT/OIDC auth (Enterprise gate, per-issuer JWKS/iss/aud, claim mapping, JWKS TTL/stale behaviour) — https://docs.litellm.ai/docs/proxy/token_auth — index
- LiteLLM OIDC model access / role permissions — https://docs.litellm.ai/docs/proxy/jwt_auth_arch — index
- LiteLLM SSO/team-claim behaviour — https://docs.litellm.ai/docs/proxy/admin_ui_sso — index
- LiteLLM virtual keys, budgets, spend (analyses checked against docs Oct 2026, secondary) — https://flatkey.ai/blog/litellm-proxy-operations-cost ; https://www.beri.net/article/best-finops-tools-ai-spend-attribution-gateway-tagging-2026 — index
- Firebase pricing (50K MAU; SAML/OIDC 50 MAU no-cost) — https://firebase.google.com/pricing — index
- Google Cloud Identity Platform pricing (Tier-1/Tier-2 rates, SMS) — https://cloud.google.com/identity-platform/pricing — index
- Microsoft Entra External ID FAQ (50,000 MAU free core; add-ons no free tier) — https://learn.microsoft.com/vi-vn/entra/external-id/customers/faq-customers — index
- Entra ID pricing/licensing guides (P1 $7/P2 $10 from 2026-07-01; External Basic $0.03/MAU, secondary) — https://www.siit.io/tools/trending/microsoft-entra-id-review ; https://samexpert.com/entra-id-licensing-guide/ — index
- Auth0 plans (Free 25,000 MAU; Essentials/Pro prices) — https://auth0.com/blog/whatever-you-are-building-auth0-has-a-plan/ ; free-plan detail incl. 1 enterprise connection — https://atyantik.com/blog/sso-cost-iam-pricing/ — index
- Auth0 custom domain requires card verification on Free — https://auth0.com/blog/seven-architectural-readiness-checks-before-production-launch/ — index
- Okta Integrator Free Plan terms (≤10 users, non-production) — https://developer.okta.com/terms/ ; Okta pricing/minimums (secondary) — https://underdefense.com/industry-pricings/okta-pricing-ultimate-guide-for-security-products/ — index
- Okta Cross App Access / ID-JAG token exchange sample — https://developer.okta.com/blog/2026/10/09/typescript-mcp-sdk-cross-app-access ; ID-JAG draft status — https://andrewdoering.org/blog/2026/cross-app-access-mcp-roadmap/ — index
- ZITADEL pricing (Free: 100 DAU, unlimited users/orgs, 3 IdPs; Pro $100/mo) — https://Zitadel.com/pricing — index
- SuperTokens pricing/self-host (secondary, vendor blog) — https://supertokens.com/blog/okta-alternatives — index
- Keycloak/self-host cost context — https://ssojet.com/blog/enterprise-authentication-for-developers-10-tools-compared — index
- VPS pricing (Hetzner CX22 ~€4.49/mo post-Apr-2026, +€0.50 IPv4) — https://bex.co/blog/2026/10/14/railway-vs-render-vs-flyio-solo-developer-hidden-costs — index
- vLLM security (multi-tenant non-isolation, cache_salt, unauthenticated endpoints, CVE-2025-46570) — https://docs.vllm.ai/en/latest/usage/security/ — index
- vLLM prefix caching / cache_salt mechanics — https://docs.vllm.ai/en/latest/design/prefix_caching/ — index
- Cloudflare AI Gateway spend limits (Access `cf.user_id` vs spoofable metadata) — https://developers.cloudflare.com/ai-gateway/features/spend-limits/ ; https://blog.cloudflare.com/ai-gateway-spend-limits/ ; limits — https://developers.cloudflare.com/ai-gateway/reference/limits/ — index
- Kong OSS vs Enterprise plugin audit (secondary) — https://dev.to/toffy/top-5-ai-gateways-for-enterprises-79c — index
- Portkey OSS limitations / hosted pricing / Palo Alto acquisition (secondary) — https://geekflare.com/open-source/portkey-gateway/ ; https://flatkey.ai/blog/ai-gateway-pricing — index
- Envoy Gateway JWT + global rate limit — https://gateway.envoyproxy.io/v1.2/tasks/traffic/global-rate-limit/ ; Envoy AI Gateway usage-based (token-cost) rate limiting — https://theagentrouter.ai/docs/0.4/capabilities/traffic/usage-based-ratelimiting/ — index
- Bifrost virtual keys/hierarchical budgets, Enterprise SSO/audit (secondary) — https://dev.to/toffy/best-ai-gateways-with-built-in-observability-governance-2026-27dg — index
