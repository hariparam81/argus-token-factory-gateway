"""Phase 1 exit gate, through the full chain (public URL -> Caddy -> shim -> LiteLLM -> vLLM).

Two tenants with different salts send the same long prefix. Expected: tenant A's repeat shows cached tokens,
tenant B's first call shows none, and LiteLLM's own response cache is off (no cache hit header, repeat call
still reaches the backend and reports usage).
Env: GATEWAY_URL, TENANT_A_KEY, GATE_B_KEY, WORKLOAD.
"""
import json
import os
import urllib.request

URL = os.environ["GATEWAY_URL"].rstrip("/") + "/v1/chat/completions"
MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"
paper = json.load(open(os.environ["WORKLOAD"]))["papers"][1]  # a different paper than Phase 0, so the cache starts cold
system = "Answer the question about the paper below. Be brief.\n\n" + paper["text"]
question = paper["questions"][0]["question"]


def call(key, **extra):
    body = {"model": MODEL, "max_tokens": 8, "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": question}], **extra}
    req = urllib.request.Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json", "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.load(r)
        headers = {k.lower(): v for k, v in r.headers.items()}
    u = out["usage"]
    return {"prompt_tokens": u["prompt_tokens"], "cached_tokens": (u.get("prompt_tokens_details") or {}).get("cached_tokens"),
            "litellm_cache_hit_header": headers.get("x-litellm-cache-key"), "call_id": headers.get("x-litellm-call-id")}


A, B = os.environ["TENANT_A_KEY"], os.environ["GATE_B_KEY"]
rows = [("A first (cold)", call(A)), ("A second (warm)", call(A)), ("B first (other salt)", call(B)), ("B second", call(B)),
        ("A client-supplied cache_salt ignored", call(A, cache_salt="attacker-chosen"))]
for label, r in rows:
    print(f"{label:40s} prompt={r['prompt_tokens']} cached={r['cached_tokens']} litellm_cache_header={r['litellm_cache_hit_header']} call_id={'yes' if r['call_id'] else 'no'}")
