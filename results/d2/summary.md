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
