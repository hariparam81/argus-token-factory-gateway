"""Tenant A batch runner: runs the QASPER workload through the public gateway with a factory-issued key.

Writes one JSON line per question (answer, tokens, cached tokens, cost, score). Sequential. Stops at the first
non-200 response and records it (this is how the D1 budget cap shows up). Env: TENANT_A_KEY, GATEWAY_URL.
Usage: python clients/tenant_a_batch.py --out results/a.jsonl [--papers ID ...] [--max-questions N]
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from qasper_score import SYSTEM_PROMPT, score  # noqa: E402

MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"


def ask(url, key, paper_text, question):
    body = {"model": MODEL, "max_tokens": 128, "temperature": 0,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT + paper_text}, {"role": "user", "content": question}]}
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", "Authorization": "Bearer " + key})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.load(r), r.headers, time.perf_counter() - t0
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), e.headers, time.perf_counter() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--papers", nargs="*")
    ap.add_argument("--max-questions", type=int)
    ap.add_argument("--workload", default=str(Path(__file__).parent.parent / "workload" / "workload.json"))
    a = ap.parse_args()
    url = os.environ["GATEWAY_URL"].rstrip("/") + "/v1/chat/completions"
    key = os.environ["TENANT_A_KEY"]
    work = json.load(open(a.workload))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    done = 0
    with open(a.out, "w") as out:
        for paper in work["papers"]:
            if a.papers and paper["paper_id"] not in a.papers:
                continue
            for q in paper["questions"]:
                if a.max_questions and done >= a.max_questions:
                    return
                status, resp, headers, secs = ask(url, key, paper["text"], q["question"])
                row = {"paper_id": paper["paper_id"], "question_id": q["question_id"], "http_status": status, "seconds": round(secs, 3)}
                if status == 200:
                    msg = resp["choices"][0]["message"]["content"]
                    u = resp["usage"]
                    row.update(answer=msg, prompt_tokens=u["prompt_tokens"], completion_tokens=u["completion_tokens"],
                               cached_tokens=(u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0,
                               cost=float(headers.get("x-litellm-response-cost") or 0), score=score(msg, q["gold"]))
                else:
                    row["error"] = resp.get("error", resp)
                out.write(json.dumps(row) + "\n")
                out.flush()
                done += 1
                print(f"{paper['paper_id']} {q['question_id'][:8]} -> {status}", flush=True)
                if status != 200:
                    print("stopping at first non-200 response")
                    return


if __name__ == "__main__":
    main()
