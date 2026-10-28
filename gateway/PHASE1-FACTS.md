# Phase 1 facts (raw record for RUN-REPORT.md)

Recorded 2026-10-28. Secret values are never written here.

## Stack as deployed (droplet argus-tfg-gw, `/opt/argus/gateway`, compose project `gateway`)
- Pinned images: `caddy:2.8.4`, `postgres:16.4`, `ghcr.io/berriai/litellm:v1.105.7`, shim built from `python:3.12.7-slim` with `fastapi==0.115.2`, `uvicorn==0.32.0`, `httpx==0.27.2`, `psycopg[binary,pool]==3.2.3`, `PyJWT[crypto]==2.9.0`.
- Network: external Docker network `argus` (172.28.0.0/24); static IPs shim .10, litellm .11, caddy .12, postgres .13, matching the egress rules. Only Caddy publishes host ports (80, 443). Health checks on postgres, litellm and shim; all healthy. Swap 2 GB present; memory after start 1.2 GB used of 3.9 GB.
- Routing: Caddy proxies `/v1/*` to the shim; any other path returns 404 (verified: `/healthz` and `/ui` 404 on the public name). LiteLLM publishes no host port.
- Secrets live only in the droplet's `/opt/argus/gateway/.env` and `registry.json` (mode 600, not in git; templates `env.example` and `registry.template.json` are committed). The shim reads the registry file mounted into the container.
- TLS: Caddy obtained a Let's Encrypt certificate for `argus-tfg.duckdns.org` on first start (issuer CN YE1, valid 2026-10-28 to 2027-01-26), through the ACME egress allowance.
- LiteLLM config: one model, pod backend `203.57.40.93:10192`, price 1.9836e-07 per token for input and output, response cache off, telemetry off. Spend logs store no prompt or response bodies (`messages` and `response` columns hold `{}`).

## Shim (gateway/shim/app.py)
- Fronts every call. Factory key path only so far: sha256 of the presented key is looked up in the registry to find tenant and subject. Unknown or missing credentials: 401, audited as rejected. Streaming requests: 400, audited as rejected. Client-supplied `cache_salt` is dropped and replaced with the tenant's registry salt (test-only `SALTING_ENABLED` switch, default true). `max_tokens` is capped at 512.
- Audit: an intent row in `argus.audit_intent` is written before forwarding (tenant, identity mode, subject, actor, model, rejected flag and reason), then updated with the HTTP status and the response id. Cost and tokens are joined from `LiteLLM_SpendLogs` on `request_id`, which equals the response body id. First version stored the `x-litellm-call-id` header, which does not match; fixed after the exit gate, so the 5 audit rows written during the gate (and one earlier 401) have no joined spend and fall outside the demo window.
- Rejections by LiteLLM (for example a non-allowlisted model, HTTP 403) are audited with the real status but `rejected` false, since only shim-level rejections are flagged.

## Phase 1 exit gate (full chain, public URL, `clients/phase1_gate.py`)
Paper 1910.06592 as system prefix (2,991 prompt tokens), `max_tokens` 8. Tenant B key was a temporary factory key under the `tenant-b` salt, deleted afterwards.

| call | cached_tokens |
|---|---|
| A first (cold) | absent (0) |
| A second | 2976 |
| B first (other salt) | absent (0) |
| B second | 2976 |
| A with client-supplied `cache_salt` | 2976 (supplied salt ignored; tenant salt applied) |

No LiteLLM cache header on any response; LiteLLM response caching is off.

## Tenant A
- Virtual key alias `tenant-a-batch`: model allowlist the one model, `max_budget` 0.05 USD with `budget_duration` 1h, `rpm_limit` 60, `tpm_limit` 300000, expires 2026-10-30T23:22:02Z. The budget is a placeholder; D1 resizes it from measured per-call cost. Key value is in the operator's local `~/.argus-secrets/tenant_a.env` as `TENANT_A_KEY`.
- Runner: `clients/tenant_a_batch.py` (scoring in `clients/qasper_score.py`), run from the Mac against the public URL.

## Smoke tests
- Three workload calls: HTTP 200, spend 0.000891, 0.000890, 0.000891 USD logged per call (nonzero), joined to audit rows (4,492 / 4,487 / 4,491 total tokens).
- `model: gpt-4o` with Tenant A's key: 403 `key_model_access_denied` from LiteLLM.
- Streaming request: 400. No credentials: 401. Both audited as rejected.
- Per-call cost is about $0.00089 (about 4.5k tokens), higher than the Phase 0 estimate of $0.00073 because the shown prompts were longer; the D1 budget will be sized from this.
