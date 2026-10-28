"""Phase 0 probe against the pod, run from the droplet (stdlib only).

1. cache test: same long prefix twice under salt A (second call should show cached tokens), then under salt B (~0).
2. TTFT proxy: wall time of a max_tokens=1 call, cold vs warm, medians over repeats.
3. throughput: all workload questions, sequential, one salt, for the tokens/hr measurement behind the model price.

Env: POD_URL (http://ip:port), VLLM_API_KEY, WORKLOAD (path to workload.json).
"""
import json
import os
import statistics
import time
import urllib.request

URL = os.environ["POD_URL"].rstrip("/") + "/v1/chat/completions"
KEY = os.environ["VLLM_API_KEY"]
MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"
work = json.load(open(os.environ["WORKLOAD"]))
paper = work["papers"][0]

SYSTEM = "Answer the question about the paper below. Be brief.\n\n" + paper["text"]


def call(question, salt, max_tokens):
    body = {"model": MODEL, "max_tokens": max_tokens, "temperature": 0,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]}
    if salt:
        body["cache_salt"] = salt
    req = urllib.request.Request(URL, json.dumps(body).encode(),
                                 {"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.load(r)
    dt = time.perf_counter() - t0
    u = out["usage"]
    cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens")
    return dt, u["prompt_tokens"], u["completion_tokens"], cached


q0 = paper["questions"][0]["question"]
res = {"paper_id": paper["paper_id"], "paper_tokens": paper["tokens"]}

# 1. cache test
rows = []
for label, salt in [("A first", "probe-salt-A"), ("A second", "probe-salt-A"), ("B first", "probe-salt-B"), ("B second", "probe-salt-B")]:
    dt, p, c, cached = call(q0, salt, 1)
    rows.append({"call": label, "seconds": round(dt, 3), "prompt_tokens": p, "cached_tokens": cached})
res["cache_test"] = rows

# 2. TTFT proxy: cold = fresh salt each time, warm = repeat of one salt (max_tokens=1)
cold, warm = [], []
for i in range(5):
    salt = f"ttft-{time.time_ns()}"
    cold.append(call(q0, salt, 1)[0])
    warm.append(call(q0, salt, 1)[0])
res["ttft_proxy_seconds"] = {"cold_median": round(statistics.median(cold), 3), "warm_median": round(statistics.median(warm), 3),
                             "cold": [round(x, 3) for x in cold], "warm": [round(x, 3) for x in warm]}

# 3. throughput over the whole workload, sequential
salt = f"throughput-{time.time_ns()}"
tot_prompt = tot_comp = tot_cached = n = 0
t0 = time.perf_counter()
for p in work["papers"]:
    SYSTEM = "Answer the question about the paper below. Be brief.\n\n" + p["text"]
    for q in p["questions"]:
        dt, pt, ct, cached = call(q["question"], salt, 256)
        tot_prompt += pt
        tot_comp += ct
        tot_cached += cached or 0
        n += 1
wall = time.perf_counter() - t0
total = tot_prompt + tot_comp
res["throughput"] = {"calls": n, "wall_seconds": round(wall, 2), "prompt_tokens": tot_prompt, "completion_tokens": tot_comp,
                     "cached_prompt_tokens": tot_cached, "total_tokens": total, "tokens_per_hour": round(total / wall * 3600)}
print(json.dumps(res, indent=1))
