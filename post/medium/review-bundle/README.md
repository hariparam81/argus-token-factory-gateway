# Argus Token Factory Gateway

A small working instance of a shared inference service, built to test a framework for running one. The framework stands on five tenets. This repository holds the code, the configuration, the full run record and the raw exports behind them.

<!-- Launch: add the Medium article link below once the post is published. -->
**Article:** *A Framework for Running a Shared Inference Service* (link added at publication)
**Companion page:** https://hariparam81.github.io/argus-token-factory-gateway/

## The five tenets

1. **Lowest cost.** Choose the model and the hardware by cost per outcome. Price the token from your own meter.
2. **Federate with the customer's identity provider.** Customers sign in with the identity they already run. The factory's part is verification.
3. **Isolate each tenant's data and cache.** One tenant's prompts leave no trace another tenant can measure.
4. **Meter and manage spend.** Every call is metered to the tenant, the user and the agent behind it. Budgets cap each level. The tenant can see where the money went.
5. **Audit every call.** Every request leaves a row that says who made it, on whose behalf, and what it cost.

## The factory gateway

Every call passes through one component before the model sees it. The factory gateway authenticates the call, resolves it to a principal (tenant, identity mode, subject, actor, allowed models, budget account, cache salt), routes it to a model, meters it, enforces budgets and rate limits, and stamps an audit row. Four identity paths lead in: a factory-issued key, a federated token from the tenant's own provider, a delegated agent acting for a user, and a capped trial credential. The design in full is in `sources/framework-report.md`.

## What was built

- **Callers** on a laptop, outside the factory: a runner for Tenant A, a runner for Tenant B, and an agent acting for Tenant B's user from the same machine.
- **Identity** on ZITADEL Cloud (free tier), acting as Tenant B's own provider.
- **The gateway** on a 4 GB DigitalOcean droplet, in Docker Compose: Caddy 2.8.4 for TLS (only `/v1/*` proxied), a 236-line authentication shim (FastAPI), LiteLLM OSS v1.105.7 for keys, budgets and the spend ledger; Postgres 16.4.
- **The endpoint** on a RunPod pod (RTX 4090): vLLM 0.10.2 serving Qwen2.5-Coder-7B-Instruct, reachable only from the gateway, behind its own API key.

## What the run showed

The workload was QASPER, a question-answering dataset built from real research papers: three papers, 33 questions, scored by token F1 against gold answers. Both tenants ran the identical set.

- Both tenants answered all 33 questions. Mean F1 was 0.456 for Tenant A and 0.457 for Tenant B. The controls did not change the work.
- **Cache isolation.** Tenant B's first call on a paper Tenant A had warmed read 0 of 4,481 cached tokens with per-tenant salting on. In a control run with salting off, the same call read 4,480 of 4,481.
- **Budget cap.** Tenant A's batch stopped at question 19 of 33 when its $0.0143 budget ran out. The overshoot was one call, $0.000029.
- **Delegated agent.** The agent wrote a three-question brief over one paper. In a rapid loop its own rate limit stopped it on call 7, at six requests per minute, while a direct call from the same user went through.
- **Identity tests.** Eleven broken or forged credentials were sent at the gateway. All eleven were refused.
- **Audit.** The demo window held 259 calls and 1,039,846 tokens, $0.206264 in total. Every call joins from the gateway's audit rows to the spend log.
- **Cost.** The metered price, derived from the pod's hourly rate and its measured throughput, was about $0.198 per million tokens. The whole run cost about $2.49.

Two deviations are recorded, not hidden. The identity provider did not advertise token exchange, so the gateway minted the delegation token itself after validating both tokens. Tenant A's own budget cap fired during cache-test setup. The affected passes were rerun at a higher cap, with the refused calls kept in the record.

## Repository layout

- `RUN-REPORT.md`: the complete run record: phases, demos, cost ledger, pitfalls.
- `gateway/`: per-phase fact records from the build.
- `results/`: per-demo outputs (budget, cache, agent, audit) and the QASPER scores.
- `exports/`: the audit table joined to the spend log, plus the raw run exports.
- `sources/`: the framework report, the evidence bank behind the tenets, and the cost-per-outcome results the model choice rests on.
- `workload/`: how the QASPER paper set was selected.
- `post/`: the article draft and its diagrams.
- `prompts/`: the three stage prompts the build, article and companion page were produced from.
- `docs/`: the companion page (framework in full, complete run record, references).

## Reproduce it

You need a RunPod account, a DigitalOcean account and a ZITADEL Cloud free-tier instance. The order of operations and the expected results are in `RUN-REPORT.md` and in the companion page. A full run should cost between $2 and $3 at October 2026 prices. Read the pitfalls section of the run report before starting; the expensive mistakes are already documented there.

## Limits

One model, one endpoint, two tenants, one agent. Salting closes the cache channel that was measured. It is not machine isolation. The endpoint's own documentation says so. Delegation used the gateway fallback described above. The metered price comes from one pod's measured throughput, with cached tokens billed at the blended rate.

## Credits

QASPER is from the Allen Institute for AI, under a CC BY 4.0 license. The served model, Qwen2.5-Coder-7B-Instruct, is under the Apache 2.0 license.