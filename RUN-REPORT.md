# RUN REPORT: argus-token-factory-gateway, Stage 1 proof of concept

Run date: 2026-10-28 to 2026-10-29 (UTC). This report is the input to Stages 2 and 3. The infrastructure was destroyed at teardown, so the raw exports under `exports/` and `results/` are the only evidence that exists.

## 1. What was built

A small multi-tenant inference front door and the proof that it works on a real workload. Tenants reach one shared vLLM endpoint only through a gateway that identifies the caller, isolates its cache, caps its spend and audits every call.

| component | where | what it does |
|---|---|---|
| Inference endpoint | RunPod pod, RTX 4090, Secure Cloud US-IL-1 | vLLM 0.10.2 serving Qwen/Qwen2.5-Coder-7B-Instruct, API key required, prefix caching on |
| Gateway host | DigitalOcean droplet, tor1, 4 GB, Ubuntu 24.04 | Docker Compose stack `gateway/compose.yaml` |
| TLS and routing | `gateway/Caddyfile` | Caddy 2.8.4 on `argus-tfg.duckdns.org`; only `/v1/*` is proxied, everything else returns 404 |
| Auth shim | `gateway/shim/app.py` | FastAPI and PyJWT; resolves the principal, overwrites `cache_salt`, caps `max_tokens`, forwards with the principal's key, writes one audit row per call |
| Model gateway | `gateway/litellm-config.yaml` | LiteLLM OSS v1.105.7 with virtual keys, budgets, rate limits and spend log |
| Database | compose service `postgres` | Postgres 16.4; LiteLLM tables plus the shim's `argus.audit_intent` |
| Egress control | `gateway/egress/` | default-deny for containers in the `DOCKER-USER` chain, ipsets for hostname destinations |
| Operations helper | `gateway/ops/set-pod-port.sh` | repoints LiteLLM and the egress rule when the pod's public port changes |
| Workload | `workload/prepare.py`, `workload/workload.json` | QASPER, 3 papers, 33 questions |
| Tenant A runner | `clients/tenant_a_batch.py`, `clients/qasper_score.py` | factory-key caller, scores answers |
| Tenant B runner | `clients/tenant_b_runner.py` | the same workload as Tenant B's federated user |
| Agent | `clients/agent/agent.py`, `idp.py`, `zitadel_login.py` | live agent on the operator's Mac acting for Tenant B's user |
| Test and demo scripts | `clients/phase1_gate.py`, `clients/phase2_negative.py`, `clients/d2_cache.py`, `clients/summarize_*.py`, `workload/phase0_probe.py` | exit gate, negative tests, D2 passes, summaries |
| Source documents | `sources/` | framework report, evidence bank, 2026 refresh, cost-per-outcome results |
| Stage prompts | `prompts/` | the three stage prompts |

The served model was selected from the author's earlier cost-per-outcome measurements (`sources/cost-per-outcome.md`): Qwen2.5-Coder-7B won two of the three measured workloads at the lowest cost per outcome (RAG document Q&A, 93.3% at $0.0165 per 1k queries; Text2SQL, 77.5% at $0.0110 per 1k queries). It is a coder model. The F1 figures below show that the workload ran. They make no model-quality claim.

Identity paths exercised: A, a factory-issued LiteLLM virtual key (Tenant A); B, federation through ZITADEL Cloud with the user's JWT (Tenant B); C, a live agent acting for Tenant B's user under delegation. Path D is designed in the framework report and was not built. The delegation used the shim-minted fallback, because token exchange was not advertised by the ZITADEL instance.

## 2. Phase 0 facts

Recorded 2026-10-28. Secret values are never written here; variable names only.

### Pod
- Tier: Secure Cloud. A Community Cloud create with `minCudaVersion` 12.8 returned "no longer any instances available" (live capacity read showed only host CUDA 12.2 on Community), so the Secure fallback was used.
- GPU: 1x RTX 4090 (24 GB), data center US-IL-1, host CUDA 13.2, 50 GB container disk.
- Price: $0.89/hr compute plus $0.007/hr container storage = $0.897/hr (console shows $0.90/hr total).
- Image: `vllm/vllm-openai:v0.10.2`. vLLM API server version reported in logs: 0.10.2 (>= 0.9.0, cache_salt supported).
- Flags: `--model Qwen/Qwen2.5-Coder-7B-Instruct --served-model-name Qwen/Qwen2.5-Coder-7B-Instruct --max-model-len 16384 --enable-prefix-caching --enable-prompt-tokens-details --host 0.0.0.0 --port 8000`; env `VLLM_API_KEY`.
- Pod history: the first pod (`fi94bbwvpdhu2z`, created 22:22:56Z) was stopped at 22:27:57Z and terminated at 22:33:40Z, and an identical pod (`v5zou7ge5bl0t6`) was created at 22:33:46Z, all under the operator's account. The operator confirmed via console screenshot that `v5zou7ge5bl0t6` is the intended pod. The first pod never reached a running container; its billed cost is read from the RunPod billing API when the ledger is built (running from 22:22:56Z to the stop at 22:27:57Z, then stopped until termination).
- The vLLM API key was passed to the create call as a plain env value, so it appears in the build session transcript. It is a throwaway key that is destroyed with the pod.

### Pod networking path (what "tenants never reach the pod directly" rests on)
- Path: public IP with TCP port mapping (preferred path), `203.57.40.93:10192` to container port 8000. Tailscale was not needed (`TS_AUTHKEY` was prepared and unused; revoke at launch cleanup).
- Enforcement: vLLM `--api-key`. From the droplet: unauthenticated `/v1/models` 401, unauthenticated `/v1/chat/completions` 401, wrong key 401, correct key 200 listing `Qwen/Qwen2.5-Coder-7B-Instruct` with `max_model_len` 16384. `/health` answers 200 without a key (vLLM does not protect it).
- The port is reachable from the public internet; the API key is the only gate, and the droplet's egress rules pin the pod address for the LiteLLM container only. The pod itself has no IP allowlist (RunPod offers none).
- The `*.proxy.runpod.net` URL was not used.

### vLLM cache checks (direct to pod, from the droplet, `workload/phase0_probe.py`)
Paper 1908.05828 as system prefix (4,447 prompt tokens), question 1, `max_tokens` 1, `temperature` 0:

| call | salt | seconds | prompt_tokens | cached_tokens |
|---|---|---|---|---|
| first | A | 3.383 | 4447 | absent (0) |
| second | A | 0.252 | 4447 | 4432 |
| first | B | 1.347 | 4447 | absent (0) |
| second | B | 0.262 | 4447 | 4432 |

- Cached-token counts are present in usage (`prompt_tokens_details.cached_tokens`) and salts separate: salt B's first call, issued after salt A had warmed the same prefix, reports no cached tokens. vLLM omits the field when the count is 0.
- TTFT proxy (wall time of a `max_tokens` 1 call, 5 repeats, fresh salt for cold): cold median 0.697 s, warm median 0.659 s. The warm repeats were noisy (0.659, 0.84, 0.777, 0.284, 0.26 s). The prefix here is about 4.4k tokens and prefill is fast on a 4090, so the timing signal is weak; cached-token counts are the primary evidence and the demo timing method needs more repeats.
- LiteLLM response caching and the full-chain two-salt test are checked at the Phase 1 exit gate.

### Pricing derivation
- Measurement: all 33 workload questions run sequentially from the droplet against the pod, one salt, `max_tokens` 256 (same conditions as the demos): 96.67 s wall, 119,269 prompt tokens (108,000 cached), 2,161 completion tokens, 121,430 total tokens, giving 4,522,034 tokens/hr.
- Price: $0.897/hr divided by 4,522,034 tokens/hr = $1.9836e-07 per token (about $0.198 per 1M tokens), applied as a blended rate to both input and output tokens (cached tokens included at the same rate).
- Implication: one workload call is about 3,680 tokens, about $0.00073; the 33-question batch is about $0.024. The D1 budget will be sized from these figures.
- The price rests on one sequential client and a mostly-cached prefix; it is a flat-rate allocation of the pod's hourly cost.

### Workload
- 33 questions across papers 1908.05828 (12), 1910.06592 (11), 1902.09666 (10) from the validation split. Source: `allenai/qasper` parquet conversion, commit `06806e4608976fc2fac0a090ac425d5b2b29caf4`, file `qasper/validation/0000.parquet`. Dataset card license tag: `cc-by-4.0`. Largest prompt estimate 4,873 tokens against `--max-model-len` 16384.

### Droplet and DNS
- DigitalOcean `argus-tfg-gw` (id 613666435), region tor1, `s-2vcpu-4gb`, Ubuntu 24.04, $24/month ($0.03571/hr per the DigitalOcean sizes API), IP 159.203.59.93, 2 GB swap via cloud-init, Docker 29.1.3. Region choice: nearest listed region offering this size to the pod's Chicago data center (no Chicago region exists).
- Deviation from the prompt: the public name is `argus-tfg.duckdns.org` (operator-created DuckDNS record) in place of `factory.harishparam.com`. It resolved to 159.203.59.93 on 8.8.8.8. TLS certificate issuance is verified when Caddy starts in Phase 1.

### Egress (containers on the `argus` Docker network, 172.28.0.0/24)
- Enforced in the `DOCKER-USER` chain through the `ARGUS-EGRESS` chain (`gateway/egress/apply-egress.sh`, systemd unit `argus-egress.service`, env in `/etc/argus/egress.env`). Rules are by source container IP: LiteLLM (.11) to the pod address and port only; shim (.10) to the `allow_zitadel` ipset on 443; Caddy (.12) to the `allow_acme` ipset on 443; all containers to the droplet's upstream resolver on port 53 and to the internal subnet; everything else REJECT. Inbound traffic to published ports is not filtered by this chain.
- Hostnames are resolved into ipsets (`hash:ip`, 3600 s timeout) by `refresh-ipsets.sh`, run at boot via the apply script, every 15 minutes by `argus-ipset-refresh.timer`, and again before each demo run (operator procedure).
- Verification from throwaway containers with the static IPs: shim to `zitadel.cloud` 302 (allowed); shim to `example.com` blocked; shim to the pod blocked; LiteLLM to the pod `/health` 200; LiteLLM to `example.com` blocked; Caddy to the ACME directory 200; Caddy to `zitadel.cloud` blocked.
- The ZITADEL ipset currently holds `zitadel.cloud`; the tenant instance host is added in Phase 2. The droplet host itself is not egress-filtered (setup needs package registries); only container egress is default-deny.

## 3. Phase 1 facts

Recorded 2026-10-28. Secret values are never written here.

### Stack as deployed (droplet argus-tfg-gw, `/opt/argus/gateway`, compose project `gateway`)
- Pinned images: `caddy:2.8.4`, `postgres:16.4`, `ghcr.io/berriai/litellm:v1.105.7`, shim built from `python:3.12.7-slim` with `fastapi==0.115.2`, `uvicorn==0.32.0`, `httpx==0.27.2`, `psycopg[binary,pool]==3.2.3`, `PyJWT[crypto]==2.9.0`.
- Network: external Docker network `argus` (172.28.0.0/24); static IPs shim .10, litellm .11, caddy .12, postgres .13, matching the egress rules. Only Caddy publishes host ports (80, 443). Health checks on postgres, litellm and shim; all healthy. Swap 2 GB present; memory after start 1.2 GB used of 3.9 GB.
- Routing: Caddy proxies `/v1/*` to the shim; any other path returns 404 (verified: `/healthz` and `/ui` 404 on the public name). LiteLLM publishes no host port.
- Secrets live only in the droplet's `/opt/argus/gateway/.env` and `registry.json` (mode 600, excluded from git; templates `env.example` and `registry.template.json` are committed). The shim reads the registry file mounted into the container.
- TLS: Caddy obtained a Let's Encrypt certificate for `argus-tfg.duckdns.org` on first start (issuer CN YE1, valid 2026-10-28 to 2027-01-26), through the ACME egress allowance.
- LiteLLM config: one model, pod backend `203.57.40.93:10192`, price 1.9836e-07 per token for input and output, response cache off, telemetry off. Spend logs store no prompt or response bodies (`messages` and `response` columns hold `{}`).

### Shim (gateway/shim/app.py)
- Fronts every call. Factory key path only so far: sha256 of the presented key is looked up in the registry to find tenant and subject. Unknown or missing credentials: 401, audited as rejected. Streaming requests: 400, audited as rejected. Client-supplied `cache_salt` is dropped and replaced with the tenant's registry salt (test-only `SALTING_ENABLED` switch, default true). `max_tokens` is capped at 512.
- Audit: an intent row in `argus.audit_intent` is written before forwarding (tenant, identity mode, subject, actor, model, rejected flag and reason), then updated with the HTTP status and the response id. Cost and tokens are joined from `LiteLLM_SpendLogs` on `request_id`, which equals the response body id. First version stored the `x-litellm-call-id` header, which does not match; fixed after the exit gate, so the 5 audit rows written during the gate (and one earlier 401) have no joined spend and fall outside the demo window.
- Rejections by LiteLLM (for example a non-allowlisted model, HTTP 403) are audited with the real status but `rejected` false, since only shim-level rejections are flagged.

### Phase 1 exit gate (full chain, public URL, `clients/phase1_gate.py`)
Paper 1910.06592 as system prefix (2,991 prompt tokens), `max_tokens` 8. Tenant B key was a temporary factory key under the `tenant-b` salt, deleted afterwards.

| call | cached_tokens |
|---|---|
| A first (cold) | absent (0) |
| A second | 2976 |
| B first (other salt) | absent (0) |
| B second | 2976 |
| A with client-supplied `cache_salt` | 2976 (supplied salt ignored; tenant salt applied) |

No LiteLLM cache header on any response; LiteLLM response caching is off.

### Tenant A
- Virtual key alias `tenant-a-batch`: model allowlist the one model, `max_budget` 0.05 USD with `budget_duration` 1h, `rpm_limit` 60, `tpm_limit` 300000, expires 2026-10-30T23:22:02Z. The budget is a placeholder; D1 resizes it from measured per-call cost. Key value is in the operator's local `~/.argus-secrets/tenant_a.env` as `TENANT_A_KEY`.
- Runner: `clients/tenant_a_batch.py` (scoring in `clients/qasper_score.py`), run from the Mac against the public URL.

### Smoke tests
- Three workload calls: HTTP 200, spend 0.000891, 0.000890, 0.000891 USD logged per call (nonzero), joined to audit rows (4,492 / 4,487 / 4,491 total tokens).
- `model: gpt-4o` with Tenant A's key: 403 `key_model_access_denied` from LiteLLM.
- Streaming request: 400. No credentials: 401. Both audited as rejected.
- Per-call cost is about $0.00089 (about 4.5k tokens), higher than the Phase 0 estimate of $0.00073 because the shown prompts were longer; the D1 budget will be sized from this.

## 4. Phase 2 facts

Recorded 2026-10-28. Secret values are never written here.

### ZITADEL (free tier, Cloud)
- Instance domain (issuer): `argus-tf-idp-3q58nr.us1.zitadel.cloud`. The organisation domain `argus-tf-idp.us1.zitadel.cloud` is a separate value used only for user login names; requests to it return "Instance not found".
- Project `397175819337762722`, device-code application client `397176372382008105`, machine user `agent` (subject `397177372589197218`), demo user subject `397175765415756585`, organisation `397175311441134377`. The operator created the account, organisation, user, project, application and machine user; the demo user has a dedicated email address that differs from the operator's personal one.
- Access token type set to JWT on both the application and the machine user (default was opaque; opaque tokens cannot be validated by the shim). Tokens are RS256 with a key id. Access token lifetime is 43,200 s (12 h).
- The Refresh Token grant had to be enabled on the application (the first renewal attempt returned `unauthorized_client: grant_type "refresh_token" not allowed`).
- Token exchange: the instance discovery document does not list `urn:ietf:params:oauth:grant-type:token-exchange`, so it was not used. **Path used: the shim-minted delegation token.**
- Egress: the instance host is in `gateway/egress/hosts-zitadel.txt`; the shim reaches the JWKS endpoint (HTTP 200) and `example.com` stays blocked.

### Delegation path (gateway/shim/app.py)
- The agent runs on the operator's Mac (`clients/agent/agent.py`, helpers in `clients/agent/idp.py`). User token from the device flow (`clients/agent/zitadel_login.py`, run once, approved by the demo user in a browser), renewed from a stored refresh token; agent token from client credentials.
- `POST /v1/delegate` with the user JWT as bearer and the agent JWT in `X-Agent-Token`: the shim validates both against the registered issuer (JWKS fetched per issuer, asymmetric algorithms only, exact `iss`, `aud` must equal the project id, `exp` required), requires the user subject and the agent subject to map to the same tenant in the operator registry, and returns an HS256 token (`iss` `argus-shim-delegation`, `aud` `argus-gateway`, `sub` user, `act.sub` agent, 300 s lifetime).
- Calls with the delegation token resolve to identity mode `delegated_agent` (subject = user, actor = agent) and are forwarded with the agent's LiteLLM key. A direct user JWT resolves to `federated_user` and is forwarded with the user's key. Tenant comes from the registry only; an `X-Tenant` header is ignored.
- Observed delegated token: `sub` 397175765415756585, `act` {sub 397177372589197218}, tenant `tenant-b`, ttl 300 s.
- First live agent run (3 questions, paper 1902.09666): 3 calls, 200, brief written; per-question F1 0.46, 0.17, 1.00.

### Tenant B objects in LiteLLM
- Team `tenant-b` (id `7220047f-c9fd-4a28-b6fa-7926744ec466`): max budget 0.20 USD, `budget_duration` 1d, model allowlist the one model.
- Keys `tenant-b-user` (60 RPM, 300000 TPM) and `tenant-b-agent` (6 RPM, 300000 TPM), both under the team, expiry 2 days. Values live only in the droplet's `registry.json`.

### Team budget verification (disposable team, deleted afterwards)
- Team max budget 0.0015 USD, two keys under it, calls of about 4,540 tokens each. key1 call1 200, key2 call2 200, then key1 call3 and key2 call4 both 422 `budget_exceeded` (team cost 0.00180071 against the 0.0015 cap). The team-level budget enforces across keys in LiteLLM v1.105.7 OSS; no per-key fallback was needed. The error text reads "Max budget: 0", a display quirk, since the cap did enforce.
- An earlier run of this test used prompts too short to reach the cap (four calls, no block) and was repeated with larger prompts.

### Negative and positive tests through the public gateway (`clients/phase2_negative.py`)
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

## 5. Phase 3 facts and demo outputs

Recorded 2026-10-29 (UTC). Raw per-call files and outputs are under `results/`; demo state changes are in `results/demo-state.log`. Secret values are never written here.

### Demo state per demo
- D1: Tenant A key `tenant-a-batch`, `max_budget` 0.0143 USD, spend reset to 0 at the start (set with `/key/update` on the key's token hash), batch run sequentially from the operator's Mac through the public URL.
- Between D1 and D2: budget reset to 0.05 USD, spend 0. Raised again to 1.00 USD (spend 0) during D2 after the setup failure below.
- D2 main sequence: vLLM restarted by RunPod pod restart at 00:23:52Z; the restart reassigned the public TCP port (10192 to 10262); `gateway/ops/set-pod-port.sh` repointed LiteLLM and the egress rule. Salting on (default).
- D2 control sequence: vLLM restarted again at 00:44:29Z (port 10262 to 10251, repointed); shim test-only switch `SALTING_ENABLED` set to false at 00:54:43Z, restored to true at 00:55:41Z.
- D3: Tenant B team `tenant-b` (max 0.20 USD), agent key 6 RPM, user key 60 RPM, delegation tokens with 300 s lifetime.

### D1: budget cap fires mid-work (`results/d1/`)
- Budget 0.0143 USD sized from per-call cost (workload about 0.024 USD in total; target stop between 40% and 70% of the 33 questions). Result: 18 questions answered (54.5%), question 19 rejected with HTTP 422 `budget_exceeded`: "Budget has been exceeded! Key=tenant-a-batch (sk-...NNjw) Current cost: 0.014328534600000003, Max budget: 0.0143". The runner stopped at the first non-200.
- Spend: per-call cost headers sum to 0.014329; the key's recorded spend is 0.0143285346; the spend log has 19 rows summing to 0.014329 (18 completed plus the rejected call at zero spend).
- Overshoot: the last accepted call (cost 0.0006010308) crossed the cap by 0.000029 USD (0.2% of the cap), one call, as expected for a sequential batch. No call ran after the cap was exceeded.
- F1 on the 18 answered (15 text-answer, 2 yes/no, 1 unanswerable): see `results/qasper/summary.txt`.

### D2: cache isolation (`results/d2/`, `results/d2/summary.md`)
Designated paper 1908.05828 (4,417 paper tokens, 12 questions, 4,481 prompt tokens per call), max_tokens 16, temperature 0, every call carries the full paper as the prefix plus one question. Within a pass, calls after the first share the prefix under the same salt, so the isolation evidence is each tenant's first call of its first pass.

| sequence | pass | first call cached tokens | pass cached share |
|---|---|---|---|
| main, salting on, cold cache after restart | Tenant A first pass | 0 of 4,481 | 91.2% (49,104 of 53,820) |
| main | Tenant B first pass (after A had warmed its own cache) | **0 of 4,481** | 91.2% |
| main | Tenant B repeats 1-5 | 4,480 of 4,481 each | 99.9% each |
| main | Tenant A repeats 1-5 (rerun) | 4,480 of 4,481 each | 99.9% each |
| control, salting off, cold cache after second restart | Tenant A first pass | 0 of 4,481 | 91.2% |
| control | Tenant B first pass | **4,480 of 4,481** | 99.9% |

- The claim-carrying comparison: Tenant B's first call reads 0 cached tokens when salting is on and 4,480 of 4,481 when salting is off.
- Timings (secondary): first calls 5.39 s (A, cold, first request after restart), 1.576 s (B, salted, other tenant warm), 5.762 s (control A, cold), 1.227 s (control B, unsalted, warm); medians of per-pass median call latency over 5 repeat passes: Tenant B 0.969 s, Tenant A 1.028 s. Every call includes the round trip from the operator's Mac through Caddy, the shim and LiteLLM (about 1 s end to end), so the prefill difference is hard to see in wall time at this prefix size. First passes are single measurements.
- Setup failure (recorded as a setup failure and excluded from the results): Tenant A's key hit its 0.05 USD cap during the first set of repeat passes (a 12-call pass costs about 0.0107 USD because cached tokens are priced at the same blended rate), so repeat 4 had 422s and repeat 5 was entirely rejected. The budget was raised to 1.00 USD and all five A repeat passes were rerun; the earlier files are in `results/d2/superseded/`. The 15 resulting 422s appear in the D4 output as Tenant A's non-OK calls.

### D3: the agent under delegation (`results/d3/`)
- Brief: the agent obtained a delegated token (`sub` 397175765415756585, `act.sub` 397177372589197218, tenant tenant-b, ttl 300 s) and answered 3 questions on paper 1902.09666 (`results/d3/agent-brief.md`).
- Rate limit: after a 65 s pause the agent looped rapid calls: calls 1-6 returned 200, call 7 returned **429** (agent key limit 6 RPM). During the throttling one plain Tenant B user call (user key) returned **200**.
- Team budget: team spend before D3 0.07691528016, after 0.0789631488, a delta of 0.00204787 USD, which equals the completed-call spend rows in the window to the last digit (agent key 10 spend rows summing 0.00204093, user key 1 row of 0.00000694). The 429 call produced a zero-spend row; the throttled call added nothing to the team's spend.
- Audit rows in the window (Tenant B): `delegation_mint` 200 x2, `delegated_agent` 200 x9 and 429 x1, `federated_user` 200 x1.

### D4: audit reconstruction (`results/d4/audit_reconstruction.sql` and `.txt`)
Window 2026-10-29T00:22:33Z to 00:57:32Z (start of D1 to end of D3, including D2). Output reproduced verbatim in the run report from `results/d4/audit_reconstruction.txt`.

| tenant | identity mode | subject | actor | calls | ok | not ok | total tokens | cost USD |
|---|---|---|---|---|---|---|---|---|
| tenant-a | factory_key | tenant-a-batch | - | 163 | 147 | 16 | 652,019 | 0.129334 |
| tenant-b | delegated_agent | 397175765415756585 | 397177372589197218 | 10 | 9 | 1 | 10,289 | 0.002041 |
| tenant-b | delegation_mint | 397175765415756585 | 397177372589197218 | 2 | 2 | 0 | 0 | 0.000000 |
| tenant-b | federated_user | 397175765415756585 | - | 84 | 84 | 0 | 377,538 | 0.074888 |

- Totals: 259 audit calls, 1,039,846 tokens, 0.206264 USD. Cross-check: LiteLLM's own spend log for the window holds 257 rows summing 0.206264 USD (259 audit calls minus the 2 delegation mints, which make no model call); 17 of those rows are zero-spend (16 Tenant A budget rejections and 1 agent rate-limit rejection).
- Not-OK outcomes inside the window: Tenant A 422 x16 (HTTP 422 `budget_exceeded` from LiteLLM: 1 in D1 and 15 in the D2 setup failure), agent 429 x1. These are rejections made by LiteLLM, so the shim's `rejected` flag is false for them.
- The 13 shim-level rejections from the Phase 2 negative tests (401, flagged `rejected`) are listed separately at the end of the output.

### QASPER scored runs (`results/qasper/`, run after D4 so they are outside its window)
- Full 33-question workload, sequential, max_tokens 128, temperature 0, each tenant through its own identity path:
  - Tenant A (factory key): 33 of 33 answered; text-answer set n=29, mean token F1 0.456; yes/no 3 of 3 correct; 1 gold-unanswerable question, which the model also declared unanswerable; 109,088 of 120,391 prompt tokens cached (90.6%); cost 0.023986 USD.
  - Tenant B (federated user): 33 of 33 answered; text-answer set n=29, mean token F1 0.457; yes/no 3 of 3; 1 gold-unanswerable, declared unanswerable; 112,416 of 120,391 cached (93.4%); cost 0.023986 USD.
- D1's partial run: 18 of 19 attempted answered; text-answer set n=15, mean F1 0.391; yes/no 2 of 2; 1 gold-unanswerable declared.
- These two runs add 66 calls and about 0.048 USD after the D4 window; they appear in the audit table but not in the D4 output.
- Scoring rule (`clients/qasper_score.py`): text questions use token F1 with SQuAD-style normalisation, maximum over annotators; yes/no questions are scored as accuracy and reported separately; gold-unanswerable questions are reported separately as whether the model declared them unanswerable. F1 here shows the workload ran and makes no model-quality claim, and is not comparable to published leaderboard numbers (different prompts and models).

### Verbatim output: D1, the rejection (`results/d1/tenant_a_d1.jsonl`, last line)

```
{"paper_id": "1910.06592", "question_id": "483a699563efcb8804e1861b18809279f21c7610", "http_status": 422, "seconds": 0.376, "error": {"message": "Budget has been exceeded! Key=tenant-a-batch (sk-...NNjw) Current cost: 0.014328534600000003, Max budget: 0.0143", "type": "budget_exceeded", "param": null, "code": "422"}}
```

### Verbatim output: D2 summary (`results/d2/summary.md`)

| pass | first call cached/prompt tokens | first call seconds | pass cached share | median call seconds |
|---|---|---|---|---|
| a_pass1 | 0/4481 | 5.39 | 49104/53820 (91.2%) | 1.054 |
| b_pass1 | 0/4481 | 1.576 | 49104/53820 (91.2%) | 1.071 |
| b_repeat1 | 4480/4481 | 1.045 | 53744/53820 (99.9%) | 0.969 |
| b_repeat2 | 4480/4481 | 1.138 | 53744/53820 (99.9%) | 1.081 |
| b_repeat3 | 4480/4481 | 1.01 | 53744/53820 (99.9%) | 0.969 |
| b_repeat4 | 4480/4481 | 1.08 | 53744/53820 (99.9%) | 1.000 |
| b_repeat5 | 4480/4481 | 1.006 | 53744/53820 (99.9%) | 0.960 |
| a_repeat1 | 4480/4481 | 1.253 | 53744/53820 (99.9%) | 1.028 |
| a_repeat2 | 4480/4481 | 0.957 | 53744/53820 (99.9%) | 1.132 |
| a_repeat3 | 4480/4481 | 1.088 | 53744/53820 (99.9%) | 1.026 |
| a_repeat4 | 4480/4481 | 1.086 | 53744/53820 (99.9%) | 0.992 |
| a_repeat5 | 4480/4481 | 1.181 | 53744/53820 (99.9%) | 1.052 |
| c_a_pass1 | 0/4481 | 5.762 | 49104/53820 (91.2%) | 1.913 |
| c_b_pass1 | 4480/4481 | 1.227 | 53744/53820 (99.9%) | 1.076 |

Tenant B repeat passes (steady state): median of the 5 per-pass median call latencies = 0.969 s; per-pass medians [0.969, 1.081, 0.969, 1.0, 0.96]

Tenant A repeat passes (steady state): median of the 5 per-pass median call latencies = 1.028 s; per-pass medians [1.028, 1.132, 1.026, 0.992, 1.052]

### Verbatim output: D3 hammer run (`results/d3/hammer-run.txt`)

```
delegated token: sub = 397175765415756585 | act = {'sub': '397177372589197218'} | tenant = tenant-b | ttl s = 300
agent call 1: 200
agent call 2: 200
agent call 3: 200
agent call 4: 200
agent call 5: 200
agent call 6: 200
agent call 7: 429
rate limit hit on call 7
plain user call during agent throttling: 200
```

### Verbatim output: D3 team budget check (`results/d3/team_budget_check.txt`)

```
-- team and key spend after
 team_alias |    spend     | max_budget 
------------+--------------+------------
 tenant-b   | 0.0789631488 |        0.2
(1 row)

   key_alias    |     spend     
----------------+---------------
 tenant-b-agent | 0.00404694072
 tenant-b-user  | 0.07491620808
(2 rows)

-- completed calls in the D3 window (spend log rows by key)
   key_alias    | calls | spend_sum  
----------------+-------+------------
 tenant-b-agent |    10 | 0.00204093
 tenant-b-user  |     1 | 0.00000694
(2 rows)

-- audit rows in the D3 window by mode and status
  identity_mode  | http_status | count 
-----------------+-------------+-------
 delegated_agent |         200 |     9
 delegated_agent |         429 |     1
 delegation_mint |         200 |     2
 federated_user  |         200 |     1
(4 rows)
```

### Verbatim output: D4 audit reconstruction (`results/d4/audit_reconstruction.txt`)

```
  tenant  |  identity_mode  |      subject       |       actor        | calls | ok  | not_ok | prompt_tokens | completion_tokens | total_tokens | cost_usd 
----------+-----------------+--------------------+--------------------+-------+-----+--------+---------------+-------------------+--------------+----------
 tenant-a | factory_key     | tenant-a-batch     | -                  |   163 | 147 |     16 |        650525 |              1494 |       652019 | 0.129334
 tenant-b | delegated_agent | 397175765415756585 | 397177372589197218 |    10 |   9 |      1 |         10203 |                86 |        10289 | 0.002041
 tenant-b | delegation_mint | 397175765415756585 | 397177372589197218 |     2 |   2 |      0 |             0 |                 0 |            0 | 0.000000
 tenant-b | federated_user  | 397175765415756585 | -                  |    84 |  84 |      0 |        376740 |               798 |       377538 | 0.074888
(4 rows)

 calls | cost_usd | total_tokens 
-------+----------+--------------
   259 | 0.206264 |      1039846
(1 row)

  tenant  |  identity_mode  | http_status | rejected |     reason     | count 
----------+-----------------+-------------+----------+----------------+-------
 tenant-a | factory_key     |         422 | f        | (from LiteLLM) |    16
 tenant-b | delegated_agent |         429 | f        | (from LiteLLM) |     1
(2 rows)

       at       |        reason         | http_status 
----------------+-----------------------+-------------
 10-29 00:18:20 | unauthenticated       |         401
 10-29 00:18:21 | unregistered_issuer   |         401
 10-29 00:18:22 | invalid_token         |         401
 10-29 00:18:22 | algorithm_not_allowed |         401
 10-29 00:18:22 | unauthenticated       |         401
 10-29 00:18:23 | token_expired         |         401
 10-29 00:18:53 | unauthenticated       |         401
 10-29 00:18:53 | unregistered_issuer   |         401
 10-29 00:18:54 | invalid_token         |         401
 10-29 00:18:54 | algorithm_not_allowed |         401
 10-29 00:18:54 | unauthenticated       |         401
 10-29 00:18:55 | token_expired         |         401
 10-29 00:18:56 | wrong_audience        |         401
(13 rows)
```

### Verbatim output: QASPER scored runs (`results/qasper/summary.txt`)

```
results/d1/tenant_a_d1.jsonl: 18/19 answered | text-answer set n=15 mean token F1=0.391 | yes/no n=2 correct=2 | unanswerable-gold n=1 model-said-unanswerable=1 | prompt tokens=71971 cached=68704 (95.5%) | cost=0.014329 USD
results/qasper/a_full.jsonl: 33/33 answered | text-answer set n=29 mean token F1=0.456 | yes/no n=3 correct=3 | unanswerable-gold n=1 model-said-unanswerable=1 | prompt tokens=120391 cached=109088 (90.6%) | cost=0.023986 USD
results/qasper/b_full.jsonl: 33/33 answered | text-answer set n=29 mean token F1=0.457 | yes/no n=3 correct=3 | unanswerable-gold n=1 model-said-unanswerable=1 | prompt tokens=120391 cached=112416 (93.4%) | cost=0.023986 USD
```

Dataset: `allenai/qasper`, parquet conversion commit `06806e4608976fc2fac0a090ac425d5b2b29caf4`, file `qasper/validation/0000.parquet`. Papers 1908.05828, 1910.06592 and 1902.09666, 33 questions. License from the dataset card tag: CC BY 4.0, credit Allen Institute for AI. The scores are as measured with this repo's prompts and a 7B coder model, and they are not comparable to published leaderboard numbers.

## 6. Cost ledger

Every figure traces to a bill, a log or a config. The pod and droplet rates come from the RunPod GPU-type read, the console and the DigitalOcean sizes API. Hours come from the timestamps in `results/demo-state.log`, `gateway/PHASE0-FACTS.md` and the RunPod audit log.

| item | basis | cost USD |
|---|---|---|
| RunPod pod 1, `fi94bbwvpdhu2z` | RunPod billing API, record for 2026-10-28; ran 22:22:56Z to 22:27:57Z, never reached a running container | 0.0742 |
| RunPod pod 2, `v5zou7ge5bl0t6` | 22:33:46Z to terminate at about 01:08:54Z, 2.586 h at $0.89/hr compute plus $0.007/hr container storage ($0.897/hr) | 2.319 |
| DigitalOcean droplet, `argus-tfg-gw` | created 22:27:18Z, deleted about 01:08:54Z, 2.693 h at $0.03571/hr (sizes API, $24/month) | 0.096 |
| ZITADEL Cloud, free tier | one organisation, one project, one application, one machine user | 0.00 |
| Tailscale | auth key prepared and not used | 0.00 |
| Domain | DuckDNS subdomain | 0.00 |
| GitHub | private repository | 0.00 |
| **Total** | | **about 2.49** |

- The RunPod billing API read at 01:09Z reports $0.0742 for pod 1 and $1.4256 for pod 2 (total $1.4997). Those pod 2 figures lag real usage: the same totals appeared at 01:03Z and at 01:09Z, while the pod ran for 2.59 hours. The pod 2 line above is rate times hours, and it is replaced by the billing API figure once the API catches up (open item below).
- The DigitalOcean invoice is not available at teardown; the droplet line is rate times hours.
- Model price applied inside the gateway: $1.9836e-07 per token, derived as $0.897/hr divided by 4,522,034 tokens/hr. Spend recorded in LiteLLM across the whole run is the metering of that price and has no bearing on any bill.

## 7. Time per phase (internal record only)

Stages 2 and 3 must not surface these figures. Times are UTC and include waiting on the operator and on pod start-up.

| phase | window | elapsed | notable waits |
|---|---|---|---|
| Input check and scaffold | 22:17Z to 22:23Z | about 6 min | operator supplied the four source files |
| Phase 0, preflight | 22:23Z to 22:55Z | about 32 min | image extraction and model load about 18 min; operator supplied the DigitalOcean token and DNS name |
| Phase 1, gateway and Tenant A | 22:55Z to 23:25Z | about 30 min | |
| Phase 2, federation and agent | 23:25Z to 00:20Z | about 55 min | operator set up ZITADEL, fixed the domain value, token types and the refresh grant, and approved the device login |
| Phase 3, demos | 00:20Z to 01:01Z | about 41 min | two vLLM restarts of about 9 and 8 minutes |
| Phase 5, export and teardown | 01:01Z to 01:09Z | about 8 min | |

Total elapsed from the source files arriving to teardown: about 2 hours 52 minutes, excluding the time to write this report.

## 8. Pitfalls and resolutions

1. **Community Cloud had no host with CUDA 12.8 or newer.** The create failed with "no longer any instances available". Resolution: the approved Secure Cloud fallback.
2. **The first pod was stopped and replaced by an identical one at the operator's console.** It stopped at 22:27:57Z, terminated at 22:33:40Z and an identical pod appeared at 22:33:46Z. Resolution: the operator confirmed the replacement and the replacement was adopted.
3. **Slow first start.** Image extraction took about 10 minutes and the first model download and load took about 8 more. A restart took about 8 minutes (weights and compilation).
4. **A pod restart reassigns the public TCP port.** It changed 10192, 10262, 10251 across two restarts. Resolution: `gateway/ops/set-pod-port.sh` repoints LiteLLM and the egress rule, and each change is in `results/demo-state.log`. An early health poll checked a stale port.
5. **Wrong audit join key.** LiteLLM's spend log `request_id` is the response body id; the `x-litellm-call-id` header holds a different value. Found at the first join, fixed in the shim. Five gate-test rows pre-date the fix and have no spend attached.
6. **ZITADEL access tokens were opaque by default.** Resolution: access token type JWT on the application and the machine user.
7. **The Refresh Token grant was not enabled on the device-code application.** Resolution: the operator enabled it.
8. **Token exchange was not advertised by the instance.** Resolution: the prepared fallback, a delegation token minted by the shim after validating both credentials. This is the path used.
9. **ZITADEL cannot issue an expired token and always puts the project in the audience.** Resolution: expiry and wrong audience were tested through a temporary registered test issuer, removed afterwards with the registry restored.
10. **Mis-sized team budget test.** The first run used prompts too short to reach the cap and showed no block. It was repeated with larger prompts and showed the block. LiteLLM's error text reads "Max budget: 0" although the cap enforced.
11. **D2 setup failure.** Tenant A's $0.05 cap was exhausted by repeat passes (cached tokens are priced at the blended rate, so a 12-call pass costs about $0.0107). Resolution: budget raised to $1.00 and the five repeat passes rerun; the 15 resulting 422s are visible in D4.
12. **Egress and DNS.** The default-deny rule needed an explicit allowance for the droplet's resolver, and the resolver appeared three times in `resolv.conf`, so the rules were deduplicated.
13. **Hostname deviation.** The public name is `argus-tfg.duckdns.org` (operator-created) in place of `factory.harishparam.com`.
14. **The vLLM API key appears in the build session transcript**, because the RunPod create call takes environment values as plain text. It is a throwaway key that was destroyed with the pod.
15. **Billing API lag** on the RunPod pod billing read (section 6).
16. **One DigitalOcean SSH key remains.** The key `argus-tfg` (a public key only) was registered for the droplet. The delete calls did not remove it, and a further retry was blocked by the permission classifier, so removal is an operator action.

## 9. Scope

This proof of concept exercises the identity layer and the gateway layer. There is no sandbox layer: no consumer code executes on factory infrastructure, so the layer that would isolate tenant-supplied code was reserved, and nothing here supports or contradicts it. Identity paths A, B and C ran live (factory key, federated user, delegated agent) and path D exists as design only in the framework report. One model was served. Calls were non-streaming, so streaming accounting is out of scope. The pod was reachable through a public TCP port protected by vLLM's API key only, with the droplet's egress rules pinning the pod address for the LiteLLM container; RunPod offers no IP allowlist, so "tenants never reach the pod directly" rests on the API key and on tenants never holding it. The delegation path used the shim fallback, which this report records as the path used.

## 10. Teardown record and open items

- Terminated: pod `v5zou7ge5bl0t6` (pod list empty on read-back) and droplet `argus-tfg-gw` (404 on read-back, no droplets on the account), at about 01:08:54Z on 2026-10-29. Pod 1 was already terminated at 22:33:40Z.
- Exports committed before teardown: `exports/audit_intent.csv`, `exports/audit_joined.csv`, `exports/spend_log_reduced.csv` (key hashes, requester addresses, prompt and response content and metadata excluded; the spend log held no prompt or response bodies in any of its 351 rows), `exports/configs/` (as-run configuration with secrets redacted), and the demo and QASPER results under `results/`.
- Sweep reference copy: a local file outside the repository at `~/.argus-secrets/SWEEP-REFERENCE.txt` (path only; 14 secret values; mode 600; never committed). It is deleted after launch in Stage 3.
- Open items for the operator: remove the `argus-tfg.duckdns.org` record; delete the DigitalOcean SSH key `argus-tfg` in the console; revoke the DigitalOcean token and the unused Tailscale key at launch cleanup; rotate or delete the ZITADEL agent credential at launch cleanup; re-read the RunPod billing API later and replace the pod 2 ledger line with its final figure.

## 11. Launch

Placeholder for Stage 3: article URL and GitHub Pages URL are recorded here after launch. Not yet published.
