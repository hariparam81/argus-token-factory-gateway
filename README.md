# argus-token-factory-gateway

A proposal for a multi-tenant inference service (a "token factory") and the record of a small proof of concept that tested it. The service rests on five tenets:

- **Lowest cost.** Choose the model and hardware by cost per outcome, and meter at a price that reflects the hardware's cost. The gateway can route each request to the cheapest model that meets the tenant's quality setting, with fallback if an endpoint fails.
- **Federate with the customer's identity provider.** Customers sign in with the identity they already run. Where a customer cannot, the factory issues scoped credentials and gives the tenant an admin path to revoke them.
- **Isolate each tenant's data and cache.** One tenant's prompts leave no trace another tenant can measure.
- **Meter and manage spend.** Every call is metered to the tenant, the user and the agent behind it, and a cap refuses the next call once the budget is gone.
- **Audit every call.** Every request leaves a row that says who made it and on whose behalf.

## Read it

1. Article: ARTICLE_URL (placeholder, filled in at launch)
2. Detailed companion page (framework, evidence, full proof-of-concept record): PAGES_URL (placeholder, filled in at launch)
3. Run report: [RUN-REPORT.md](RUN-REPORT.md)

## Status

I stood up a proof of concept to replicate the framework as closely as a small instance allows, then ran a real workload through it to test and validate the design. No endpoint is live, and nothing in this repository points at one. Three identity paths ran live: a factory-issued key, a federated user through ZITADEL Cloud, and an agent acting for that user under delegation. The fourth path, a trial tier, exists as design only. The run exercised the identity and gateway layers, and there is no sandbox layer. Automatic model routing, failover and guardrails are described in the design and were not tested. The raw exports under `exports/` and `results/` are the evidence.

## What is in the repo

| path | contents |
|---|---|
| `RUN-REPORT.md` | The full record of the run: facts, demo outputs, cost ledger, pitfalls, scope |
| `docs/` | The standalone companion page (`index.html`), served by GitHub Pages |
| `post/html-src/` | Source, diagram SVGs and build script for the companion page (`python3 post/html-src/build.py`) |
| `gateway/` | As-run configuration: Docker Compose stack, Caddyfile, LiteLLM config, the auth shim (`shim/app.py`), egress rules, templates for secrets, fact records |
| `clients/` | Tenant runners, the exit-gate and negative tests, the cache demo scripts, scoring, and the agent |
| `workload/` | QASPER workload preparation, the selected questions and the preflight probe |
| `results/` | Raw demo outputs: D1 budget cap, D2 cache isolation, D3 agent under delegation, D4 audit reconstruction, QASPER scores |
| `exports/` | Audit and spend-log exports, and redacted as-run configs |
| `sources/` | The research documents behind the design: framework report, evidence bank, 2026 refresh, cost-per-outcome results |
| `prompts/` | The three stage prompts that drove the build |

## How the POC was run

One RTX 4090 on RunPod served Qwen2.5-Coder-7B-Instruct with vLLM 0.10.2 (prefix caching on, API key required). A small DigitalOcean droplet ran Caddy, an auth shim, LiteLLM (open-source tier) and Postgres under Docker Compose, with default-deny egress for the containers. Tenant A used a factory key. Tenant B used ZITADEL Cloud's free tier, and its agent ran from a client interface and reached the gateway through its public URL. The shim validated tokens, overwrote each tenant's `cache_salt`, capped request size and wrote an audit row per call. The workload was 33 QASPER questions over three papers. To rebuild it, start from `gateway/compose.yaml`, `gateway/env.example` and `gateway/registry.template.json`, then run the scripts in `clients/` in the order given in section 6 of the companion page. The run cost about $2.49.

## Credits

- Dataset: [QASPER](https://huggingface.co/datasets/allenai/qasper) from the Allen Institute for AI, CC BY 4.0.
- Model: [Qwen2.5-Coder-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct), Apache 2.0.
