# Phase 3 facts (raw record for RUN-REPORT.md)

Recorded 2026-10-29 (UTC). Raw per-call files and outputs are under `results/`; demo state changes are in `results/demo-state.log`. Secret values are never written here.

## Demo state per demo
- D1: Tenant A key `tenant-a-batch`, `max_budget` 0.0143 USD, spend reset to 0 at the start (set with `/key/update` on the key's token hash), batch run sequentially from the operator's Mac through the public URL.
- Between D1 and D2: budget reset to 0.05 USD, spend 0. Raised again to 1.00 USD (spend 0) during D2 after the setup failure below.
- D2 main sequence: vLLM restarted by RunPod pod restart at 00:23:52Z; the restart reassigned the public TCP port (10192 to 10262); `gateway/ops/set-pod-port.sh` repointed LiteLLM and the egress rule. Salting on (default).
- D2 control sequence: vLLM restarted again at 00:44:29Z (port 10262 to 10251, repointed); shim test-only switch `SALTING_ENABLED` set to false at 00:54:43Z, restored to true at 00:55:41Z.
- D3: Tenant B team `tenant-b` (max 0.20 USD), agent key 6 RPM, user key 60 RPM, delegation tokens with 300 s lifetime.

## D1: budget cap fires mid-work (`results/d1/`)
- Budget 0.0143 USD sized from per-call cost (workload about 0.024 USD in total; target stop between 40% and 70% of the 33 questions). Result: 18 questions answered (54.5%), question 19 rejected with HTTP 422 `budget_exceeded`: "Budget has been exceeded! Key=tenant-a-batch (sk-...NNjw) Current cost: 0.014328534600000003, Max budget: 0.0143". The runner stopped at the first non-200.
- Spend: per-call cost headers sum to 0.014329; the key's recorded spend is 0.0143285346; the spend log has 19 rows summing to 0.014329 (18 completed plus the rejected call at zero spend).
- Overshoot: the last accepted call (cost 0.0006010308) crossed the cap by 0.000029 USD (0.2% of the cap), one call, as expected for a sequential batch. No call ran after the cap was exceeded.
- F1 on the 18 answered (15 text-answer, 2 yes/no, 1 unanswerable): see `results/qasper/summary.txt`.

## D2: cache isolation (`results/d2/`, `results/d2/summary.md`)
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
- Setup failure (recorded, not a result): Tenant A's key hit its 0.05 USD cap during the first set of repeat passes (a 12-call pass costs about 0.0107 USD because cached tokens are priced at the same blended rate), so repeat 4 had 422s and repeat 5 was entirely rejected. The budget was raised to 1.00 USD and all five A repeat passes were rerun; the earlier files are in `results/d2/superseded/`. The 15 resulting 422s appear in the D4 output as Tenant A's non-OK calls.

## D3: the agent under delegation (`results/d3/`)
- Brief: the agent obtained a delegated token (`sub` 397175765415756585, `act.sub` 397177372589197218, tenant tenant-b, ttl 300 s) and answered 3 questions on paper 1902.09666 (`results/d3/agent-brief.md`).
- Rate limit: after a 65 s pause the agent looped rapid calls: calls 1-6 returned 200, call 7 returned **429** (agent key limit 6 RPM). During the throttling one plain Tenant B user call (user key) returned **200**.
- Team budget: team spend before D3 0.07691528016, after 0.0789631488, a delta of 0.00204787 USD, which equals the completed-call spend rows in the window to the last digit (agent key 10 spend rows summing 0.00204093, user key 1 row of 0.00000694). The 429 call produced a zero-spend row; the throttled call added nothing to the team's spend.
- Audit rows in the window (Tenant B): `delegation_mint` 200 x2, `delegated_agent` 200 x9 and 429 x1, `federated_user` 200 x1.

## D4: audit reconstruction (`results/d4/audit_reconstruction.sql` and `.txt`)
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

## QASPER scored runs (`results/qasper/`, run after D4 so they are outside its window)
- Full 33-question workload, sequential, max_tokens 128, temperature 0, each tenant through its own identity path:
  - Tenant A (factory key): 33 of 33 answered; text-answer set n=29, mean token F1 0.456; yes/no 3 of 3 correct; 1 gold-unanswerable question, which the model also declared unanswerable; 109,088 of 120,391 prompt tokens cached (90.6%); cost 0.023986 USD.
  - Tenant B (federated user): 33 of 33 answered; text-answer set n=29, mean token F1 0.457; yes/no 3 of 3; 1 gold-unanswerable, declared unanswerable; 112,416 of 120,391 cached (93.4%); cost 0.023986 USD.
- D1's partial run: 18 of 19 attempted answered; text-answer set n=15, mean F1 0.391; yes/no 2 of 2; 1 gold-unanswerable declared.
- These two runs add 66 calls and about 0.048 USD after the D4 window; they appear in the audit table but not in the D4 output.
- Scoring rule (`clients/qasper_score.py`): text questions use token F1 with SQuAD-style normalisation, maximum over annotators; yes/no questions are scored as accuracy and reported separately; gold-unanswerable questions are reported separately as whether the model declared them unanswerable. F1 here shows the workload ran, not a model-quality claim, and is not comparable to published leaderboard numbers (different prompts and models).
