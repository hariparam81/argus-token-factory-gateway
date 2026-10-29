# Phase 2 facts (raw record for RUN-REPORT.md)

Recorded 2026-10-28. Secret values are never written here.

## ZITADEL (free tier, Cloud)
- Instance domain (issuer): `argus-tf-idp-3q58nr.us1.zitadel.cloud`. The organisation domain `argus-tf-idp.us1.zitadel.cloud` is a separate value used only for user login names; requests to it return "Instance not found".
- Project `397175819337762722`, device-code application client `397176372382008105`, machine user `agent` (subject `397177372589197218`), demo user subject `397175765415756585`, organisation `397175311441134377`. The operator created the account, organisation, user, project, application and machine user; the demo user has a dedicated email, not the operator's personal one.
- Access token type set to JWT on both the application and the machine user (default was opaque; opaque tokens cannot be validated by the shim). Tokens are RS256 with a key id. Access token lifetime is 43,200 s (12 h).
- The Refresh Token grant had to be enabled on the application (the first renewal attempt returned `unauthorized_client: grant_type "refresh_token" not allowed`).
- Token exchange: the instance discovery document does not list `urn:ietf:params:oauth:grant-type:token-exchange`, so it was not used. **Path used: the shim-minted delegation token.**
- Egress: the instance host is in `gateway/egress/hosts-zitadel.txt`; the shim reaches the JWKS endpoint (HTTP 200) and `example.com` stays blocked.

## Delegation path (gateway/shim/app.py)
- The agent runs on the operator's Mac (`clients/agent/agent.py`, helpers in `clients/agent/idp.py`). User token from the device flow (`clients/agent/zitadel_login.py`, run once, approved by the demo user in a browser), renewed from a stored refresh token; agent token from client credentials.
- `POST /v1/delegate` with the user JWT as bearer and the agent JWT in `X-Agent-Token`: the shim validates both against the registered issuer (JWKS fetched per issuer, asymmetric algorithms only, exact `iss`, `aud` must equal the project id, `exp` required), requires the user subject and the agent subject to map to the same tenant in the operator registry, and returns an HS256 token (`iss` `argus-shim-delegation`, `aud` `argus-gateway`, `sub` user, `act.sub` agent, 300 s lifetime).
- Calls with the delegation token resolve to identity mode `delegated_agent` (subject = user, actor = agent) and are forwarded with the agent's LiteLLM key. A direct user JWT resolves to `federated_user` and is forwarded with the user's key. Tenant comes from the registry only; an `X-Tenant` header is ignored.
- Observed delegated token: `sub` 397175765415756585, `act` {sub 397177372589197218}, tenant `tenant-b`, ttl 300 s.
- First live agent run (3 questions, paper 1902.09666): 3 calls, 200, brief written; per-question F1 0.46, 0.17, 1.00.

## Tenant B objects in LiteLLM
- Team `tenant-b` (id `7220047f-c9fd-4a28-b6fa-7926744ec466`): max budget 0.20 USD, `budget_duration` 1d, model allowlist the one model.
- Keys `tenant-b-user` (60 RPM, 300000 TPM) and `tenant-b-agent` (6 RPM, 300000 TPM), both under the team, expiry 2 days. Values live only in the droplet's `registry.json`.

## Team budget verification (disposable team, deleted afterwards)
- Team max budget 0.0015 USD, two keys under it, calls of about 4,540 tokens each. key1 call1 200, key2 call2 200, then key1 call3 and key2 call4 both 422 `budget_exceeded` (team cost 0.00180071 against the 0.0015 cap). The team-level budget enforces across keys in LiteLLM v1.105.7 OSS; no per-key fallback was needed. The error text reads "Max budget: 0", a display quirk, since the cap did enforce.
- An earlier run of this test used prompts too short to reach the cap (four calls, no block) and was repeated with larger prompts.

## Negative and positive tests through the public gateway (`clients/phase2_negative.py`)
All 11 passed on the final run:

| case | result |
|---|---|
| federated user call | 200 |
| delegation mint (user + agent) | 200 |
| delegated agent call | 200 |
| no token | 401 `unauthenticated` |
| unregistered issuer | 401 `unregistered_issuer` |
| tampered payload (real token, altered subject) | 401 `invalid_token` |
| disallowed algorithm (HS256 under the real issuer) | 401 `algorithm_not_allowed` |
| tenant claimed by header only (`X-Tenant`) | 401 `unauthenticated` |
| Tenant A key plus `X-Tenant: tenant-b` | 200, recorded as tenant-a (header ignored) |
| expired token | 401 `token_expired` |
| wrong audience | 401 `wrong_audience` |

- Method note: ZITADEL cannot issue an expired token, and it always adds the project to the audience of tokens for an app in that project, so a real wrong-audience token could not be minted (a first attempt using a narrower scope was still accepted, because the project stays in the audience). Expiry and wrong audience were therefore exercised through a temporary registered test issuer (RSA key generated for the run, JWKS served from a throwaway container on the internal network at 172.28.0.20, removed afterwards; registry restored and confirmed).
- Every rejection appears in `argus.audit_intent` with `rejected` true and its reason; tampered-token and other rejections carry no tenant because no principal was resolved. The first run of the test script also left one extra accepted `federated_user` row from the narrow-scope attempt.
