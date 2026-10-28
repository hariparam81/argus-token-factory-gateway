"""Auth shim: fronts every call to LiteLLM.

Resolves the principal, overwrites cache_salt with the tenant's secret salt, caps max_tokens, forwards with the
principal's LiteLLM key, and writes one audit intent row per call (including rejected calls). Token and cost
figures are joined later from LiteLLM's spend logs by call id; this service never computes cost.
Non-streaming only.
"""
import hashlib
import json
import os
import uuid

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from psycopg_pool import AsyncConnectionPool

LITELLM_URL = os.environ["LITELLM_URL"]
SALTING_ENABLED = os.environ.get("SALTING_ENABLED", "true").lower() == "true"  # test-only switch for the D2 control
MAX_TOKENS_CAP = int(os.environ.get("MAX_TOKENS_CAP", "512"))
REGISTRY = json.load(open(os.environ["REGISTRY_FILE"]))

pool = AsyncConnectionPool(os.environ["DATABASE_URL"], open=False, min_size=1, max_size=4)
http = httpx.AsyncClient(timeout=120)
app = FastAPI()

SCHEMA = """
CREATE SCHEMA IF NOT EXISTS argus;
CREATE TABLE IF NOT EXISTS argus.audit_intent (
  id uuid PRIMARY KEY,
  ts timestamptz NOT NULL DEFAULT now(),
  tenant text, identity_mode text, subject text, actor text, model text,
  litellm_call_id text, rejected boolean NOT NULL DEFAULT false, reject_reason text, http_status int
);
"""


@app.on_event("startup")
async def startup():
    await pool.open()
    async with pool.connection() as conn:
        await conn.execute(SCHEMA)


async def audit_insert(rid, principal, model, rejected=False, reason=None, status=None):
    p = principal or {}
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO argus.audit_intent (id, tenant, identity_mode, subject, actor, model, rejected, reject_reason, http_status)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (rid, p.get("tenant"), p.get("identity_mode"), p.get("subject"), p.get("actor"), model, rejected, reason, status))


async def audit_finish(rid, call_id, status):
    async with pool.connection() as conn:
        await conn.execute("UPDATE argus.audit_intent SET litellm_call_id=%s, http_status=%s WHERE id=%s", (call_id, status, rid))


def resolve_factory_key(token):
    entry = REGISTRY["factory_keys"].get(hashlib.sha256(token.encode()).hexdigest())
    if not entry:
        return None
    return {"tenant": entry["tenant"], "identity_mode": "factory_key", "subject": entry["subject"], "actor": None}


def reject(status, message):
    return JSONResponse({"error": {"message": message, "type": "auth_error" if status == 401 else "invalid_request"}}, status_code=status)


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.api_route("/v1/{path:path}", methods=["GET", "POST"])
async def proxy(path: str, request: Request):
    rid = uuid.uuid4()
    if path not in ("chat/completions", "models"):
        await audit_insert(rid, None, None, True, "path_not_allowed", 404)
        return reject(404, "not found")

    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else ""
    principal = resolve_factory_key(token) if token and token.count(".") != 2 else None
    if principal is None:
        await audit_insert(rid, None, None, True, "unauthenticated", 401)
        return reject(401, "invalid or missing credentials")

    if request.method == "GET":
        resp = await http.get(f"{LITELLM_URL}/v1/{path}", headers={"authorization": auth})
        await audit_insert(rid, principal, None, False, None, resp.status_code)
        return Response(resp.content, resp.status_code, media_type="application/json")

    try:
        body = await request.json()
    except Exception:
        await audit_insert(rid, principal, None, True, "bad_json", 400)
        return reject(400, "body must be JSON")
    model = body.get("model")
    if body.get("stream"):
        await audit_insert(rid, principal, model, True, "streaming_unsupported", 400)
        return reject(400, "streaming is not supported")

    body.pop("cache_salt", None)  # never client-supplied
    if SALTING_ENABLED:
        body["cache_salt"] = REGISTRY["tenants"][principal["tenant"]]["salt"]
    body["max_tokens"] = min(int(body.get("max_tokens") or MAX_TOKENS_CAP), MAX_TOKENS_CAP)

    await audit_insert(rid, principal, model)
    resp = await http.post(f"{LITELLM_URL}/v1/chat/completions", json=body, headers={"authorization": auth})
    # LiteLLM's spend log request_id is the response body id, so that is the join key.
    try:
        call_id = resp.json().get("id")
    except ValueError:
        call_id = None
    await audit_finish(rid, call_id or resp.headers.get("x-litellm-call-id"), resp.status_code)
    passthrough = {k: v for k, v in resp.headers.items() if k.lower() == "x-litellm-response-cost"}
    return Response(resp.content, resp.status_code, media_type="application/json", headers=passthrough)
