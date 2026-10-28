# Phase 0 facts (raw record for RUN-REPORT.md)

Recorded 2026-10-28. Secret values are never written here; variable names only.

## Pod
- Tier: Secure Cloud. A Community Cloud create with `minCudaVersion` 12.8 returned "no longer any instances available" (live capacity read showed only host CUDA 12.2 on Community), so the Secure fallback was used.
- GPU: 1x RTX 4090 (24 GB), data center US-IL-1, host CUDA 13.2, 50 GB container disk.
- Price: $0.89/hr compute plus $0.007/hr container storage = $0.897/hr (console shows $0.90/hr total).
- Image: `vllm/vllm-openai:v0.10.2`. vLLM API server version reported in logs: 0.10.2 (>= 0.9.0, cache_salt supported).
- Flags: `--model Qwen/Qwen2.5-Coder-7B-Instruct --served-model-name Qwen/Qwen2.5-Coder-7B-Instruct --max-model-len 16384 --enable-prefix-caching --enable-prompt-tokens-details --host 0.0.0.0 --port 8000`; env `VLLM_API_KEY`.
- Pod history: the first pod (`fi94bbwvpdhu2z`, created 22:22:56Z) was stopped at 22:27:57Z and terminated at 22:33:40Z, and an identical pod (`v5zou7ge5bl0t6`) was created at 22:33:46Z, all under the operator's account. The operator confirmed via console screenshot that `v5zou7ge5bl0t6` is the intended pod. The first pod never reached a running container; its billed cost is read from the RunPod billing API when the ledger is built (running from 22:22:56Z to the stop at 22:27:57Z, then stopped until termination).
- The vLLM API key was passed to the create call as a plain env value, so it appears in the build session transcript. It is a throwaway key that is destroyed with the pod.

## Pod networking path (what "tenants never reach the pod directly" rests on)
- Path: public IP with TCP port mapping (preferred path), `203.57.40.93:10192` to container port 8000. Tailscale was not needed (`TS_AUTHKEY` was prepared and unused; revoke at launch cleanup).
- Enforcement: vLLM `--api-key`. From the droplet: unauthenticated `/v1/models` 401, unauthenticated `/v1/chat/completions` 401, wrong key 401, correct key 200 listing `Qwen/Qwen2.5-Coder-7B-Instruct` with `max_model_len` 16384. `/health` answers 200 without a key (vLLM does not protect it).
- The port is reachable from the public internet; the API key is the only gate, and the droplet's egress rules pin the pod address for the LiteLLM container only. The pod itself has no IP allowlist (RunPod offers none).
- The `*.proxy.runpod.net` URL was not used.

## vLLM cache checks (direct to pod, from the droplet, `workload/phase0_probe.py`)
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

## Pricing derivation
- Measurement: all 33 workload questions run sequentially from the droplet against the pod, one salt, `max_tokens` 256 (same conditions as the demos): 96.67 s wall, 119,269 prompt tokens (108,000 cached), 2,161 completion tokens, 121,430 total tokens, giving 4,522,034 tokens/hr.
- Price: $0.897/hr divided by 4,522,034 tokens/hr = $1.9836e-07 per token (about $0.198 per 1M tokens), applied as a blended rate to both input and output tokens (cached tokens included at the same rate).
- Implication: one workload call is about 3,680 tokens, about $0.00073; the 33-question batch is about $0.024. The D1 budget will be sized from these figures.
- The price rests on one sequential client and a mostly-cached prefix; it is a flat-rate allocation of the pod's hourly cost, not a market price.

## Workload
- 33 questions across papers 1908.05828 (12), 1910.06592 (11), 1902.09666 (10) from the validation split. Source: `allenai/qasper` parquet conversion, commit `06806e4608976fc2fac0a090ac425d5b2b29caf4`, file `qasper/validation/0000.parquet`. Dataset card license tag: `cc-by-4.0`. Largest prompt estimate 4,873 tokens against `--max-model-len` 16384.

## Droplet and DNS
- DigitalOcean `argus-tfg-gw` (id 613666435), region tor1, `s-2vcpu-4gb`, Ubuntu 24.04, $24/month ($0.03571/hr per the DigitalOcean sizes API), IP 159.203.59.93, 2 GB swap via cloud-init, Docker 29.1.3. Region choice: nearest listed region offering this size to the pod's Chicago data center (no Chicago region exists).
- Deviation from the prompt: the public name is `argus-tfg.duckdns.org` (operator-created DuckDNS record) instead of `factory.harishparam.com`. It resolved to 159.203.59.93 on 8.8.8.8. TLS certificate issuance is verified when Caddy starts in Phase 1.

## Egress (containers on the `argus` Docker network, 172.28.0.0/24)
- Enforced in the `DOCKER-USER` chain through the `ARGUS-EGRESS` chain (`gateway/egress/apply-egress.sh`, systemd unit `argus-egress.service`, env in `/etc/argus/egress.env`). Rules are by source container IP: LiteLLM (.11) to the pod address and port only; shim (.10) to the `allow_zitadel` ipset on 443; Caddy (.12) to the `allow_acme` ipset on 443; all containers to the droplet's upstream resolver on port 53 and to the internal subnet; everything else REJECT. Inbound traffic to published ports is not filtered by this chain.
- Hostnames are resolved into ipsets (`hash:ip`, 3600 s timeout) by `refresh-ipsets.sh`, run at boot via the apply script, every 15 minutes by `argus-ipset-refresh.timer`, and again before each demo run (operator procedure).
- Verification from throwaway containers with the static IPs: shim to `zitadel.cloud` 302 (allowed); shim to `example.com` blocked; shim to the pod blocked; LiteLLM to the pod `/health` 200; LiteLLM to `example.com` blocked; Caddy to the ACME directory 200; Caddy to `zitadel.cloud` blocked.
- The ZITADEL ipset currently holds `zitadel.cloud`; the tenant instance host is added in Phase 2. The droplet host itself is not egress-filtered (setup needs package registries); only container egress is default-deny.
