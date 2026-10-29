"""Client C: a live agent acting for Tenant B's user, run from the operator's Mac against the public gateway.

Flow: user token (ZITADEL, device flow renewed from the stored refresh token) + the agent's own credential
(ZITADEL client credentials) -> POST /v1/delegate (shim fallback for token exchange) -> delegated calls.
Task: answer 3 QASPER questions and write a short answers brief.
Modes: default runs the brief; --hammer then loops until the agent's key returns 429 and makes one plain
user call during the throttling (D3).
Env: GATEWAY_URL (default from tenant_a.env is reused for convenience).
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
sys.path.insert(0, str(Path(__file__).parent.parent))
import idp  # noqa: E402
from qasper_score import SYSTEM_PROMPT, score  # noqa: E402

MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"
GATEWAY = os.environ.get("GATEWAY_URL", "https://argus-tfg.duckdns.org").rstrip("/")
PAPER_ID = "1902.09666"  # not the paper designated for the D2 cache demo
N_QUESTIONS = 3


def call(path, body, token, extra_headers=None):
    req = urllib.request.Request(GATEWAY + path, json.dumps(body).encode(),
                                 {"Content-Type": "application/json", "Authorization": "Bearer " + token, **(extra_headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def delegated_token():
    s, d = call("/v1/delegate", {}, idp.user_token(), {"X-Agent-Token": idp.agent_token()})
    if s != 200:
        raise SystemExit(f"delegation refused: {s} {d}")
    return d["access_token"]


def ask(token, paper, question):
    return call("/v1/chat/completions", {"model": MODEL, "max_tokens": 128, "temperature": 0,
                                         "messages": [{"role": "system", "content": SYSTEM_PROMPT + paper["text"]},
                                                      {"role": "user", "content": question}]}, token)


def brief(paper, token):
    lines = [f"# Answers brief: {paper['title']}", "", f"Paper {paper['paper_id']}. Prepared by the agent on behalf of the user.", ""]
    for q in paper["questions"][:N_QUESTIONS]:
        s, r = ask(token, paper, q["question"])
        if s != 200:
            raise SystemExit(f"call failed: {s} {r}")
        ans = r["choices"][0]["message"]["content"].strip()
        sc = score(ans, q["gold"])
        lines += [f"**Q:** {q['question']}", f"**A:** {ans}", f"_tokens: {r['usage']['total_tokens']}, id: {r['id']}, scoring: {sc}_", ""]
    return "\n".join(lines)


def hammer(token):
    """Fire the agent's delegated calls rapidly until the agent key's rate limit answers 429."""
    work = json.load(open(Path(__file__).parent.parent.parent / "workload" / "workload.json"))
    paper = next(p for p in work["papers"] if p["paper_id"] == PAPER_ID)
    q = paper["questions"][0]["question"]
    sent = 0
    first_429 = None
    while sent < 60:
        sent += 1
        s, r = call("/v1/chat/completions", {"model": MODEL, "max_tokens": 4,
                                             "messages": [{"role": "user", "content": q}]}, token)
        print(f"agent call {sent}: {s}", flush=True)
        if s == 429:
            first_429 = sent
            break
    print("rate limit hit on call", first_429)
    s, r = call("/v1/chat/completions", {"model": MODEL, "max_tokens": 4, "messages": [{"role": "user", "content": "Say hi"}]}, idp.user_token())
    print("plain user call during agent throttling:", s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hammer", action="store_true")
    ap.add_argument("--out", default="results/agent-brief.md")
    a = ap.parse_args()
    token = delegated_token()
    claims = idp.jwt_claims(token)
    print("delegated token: sub =", claims["sub"], "| act =", claims["act"], "| tenant =", claims["tenant"], "| ttl s =", claims["exp"] - claims["iat"])
    if a.hammer:
        hammer(token)
        return
    work = json.load(open(Path(__file__).parent.parent.parent / "workload" / "workload.json"))
    paper = next(p for p in work["papers"] if p["paper_id"] == PAPER_ID)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    text = brief(paper, token)
    Path(a.out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
