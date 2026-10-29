"""D2 pass runner: one pass over the designated paper's questions for one tenant, per-call cached tokens and latency.

Identity: 'a' = Tenant A factory key; 'b' = Tenant B's user via ZITADEL JWT (federated_user).
Every call carries the full paper text as the shared prefix plus one question; max_tokens is 16 and temperature 0
so latency mostly reflects prefill. Within one pass, calls after the first share the prefix under the same salt,
so the evidence for isolation is the FIRST call of each tenant's first pass.
Usage: python clients/d2_cache.py --identity a --label a_pass1 [--paper 1908.05828] [--repeat N]
"""
import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "agent"))
from qasper_score import SYSTEM_PROMPT  # noqa: E402

MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"
GATEWAY = os.environ.get("GATEWAY_URL", "https://argus-tfg.duckdns.org").rstrip("/")


def token_for(identity):
    if identity == "a":
        return os.environ["TENANT_A_KEY"]
    import idp
    return idp.user_token()


def one_pass(identity, paper):
    token = token_for(identity)
    rows = []
    for i, q in enumerate(paper["questions"]):
        body = {"model": MODEL, "max_tokens": 16, "temperature": 0,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT + paper["text"]}, {"role": "user", "content": q["question"]}]}
        req = urllib.request.Request(GATEWAY + "/v1/chat/completions", json.dumps(body).encode(),
                                     {"Content-Type": "application/json", "Authorization": "Bearer " + token})
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                status, resp = r.status, json.load(r)
        except urllib.error.HTTPError as e:
            status, resp = e.code, json.loads(e.read() or b"{}")
        dt = time.perf_counter() - t0
        u = resp.get("usage", {})
        rows.append({"call": i + 1, "status": status, "seconds": round(dt, 3), "prompt_tokens": u.get("prompt_tokens"),
                     "cached_tokens": (u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0, "id": resp.get("id")})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--identity", choices=["a", "b"], required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--paper", default="1908.05828")
    ap.add_argument("--repeat", type=int, default=1)
    a = ap.parse_args()
    paper = next(p for p in json.load(open(HERE.parent / "workload" / "workload.json"))["papers"] if p["paper_id"] == a.paper)
    out = HERE.parent / "results" / "d2"
    out.mkdir(parents=True, exist_ok=True)
    medians = []
    for n in range(1, a.repeat + 1):
        label = a.label if a.repeat == 1 else f"{a.label}{n}"
        rows = one_pass(a.identity, paper)
        (out / f"{label}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        pt = sum(r["prompt_tokens"] or 0 for r in rows)
        ct = sum(r["cached_tokens"] for r in rows)
        med = statistics.median(r["seconds"] for r in rows)
        medians.append(med)
        print(f"{label}: first call cached={rows[0]['cached_tokens']}/{rows[0]['prompt_tokens']} ({rows[0]['seconds']}s) | "
              f"pass cached share={ct}/{pt}={(ct / pt if pt else 0):.1%} | median call {med}s | statuses={sorted(set(r['status'] for r in rows))}")
    if a.repeat > 1:
        print(f"median of per-pass median latency over {a.repeat} passes: {statistics.median(medians)}s")


if __name__ == "__main__":
    main()
