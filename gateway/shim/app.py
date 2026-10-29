"""Auth shim: fronts every call to LiteLLM.

Resolves the principal, overwrites cache_salt with the tenant's secret salt, caps max_tokens, forwards with the
principal's LiteLLM key, and writes one audit intent row per call (including rejected calls). Token and cost
figures are joined later from LiteLLM's spend logs by response id; this service never computes cost.
Non-streaming only.

Identity modes: factory_key (LiteLLM virtual key), federated_user (IdP JWT), delegated_agent (shim-minted
delegation token after validating the user's JWT and the agent's JWT; used because the IdP's token exchange is
not enabled on this instance).
"""
import hashlib
import json
import os
import time
import uuid

import anyio
import httpx
import jwt
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from jwt import PyJWKClient
from psycopg_pool import AsyncConnectionPool

LITELLM_URL = os.environ["LITELLM_URL"]
SALTING_ENABLED = os.environ.get("SALTING_ENABLED", "true").lower() == "true"  # test-only switch for the D2 control
MAX_TOKENS_CAP = int(os.environ.get("MAX_TOKENS_CAP", "512"))
DELEGATION_SECRET = os.environ["DELEGATION_SECRET"]
DELEGATION_TTL = int(os.environ.get("DELEGATION_TTL", "300"))
DELEGATION_ISS = "argus-shim-delegation"
ASYMMETRIC = ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "EdDSA"]
REGISTRY = json.load(open(os.environ["REGISTRY_FILE"]))

pool = AsyncConnectionPool(os.environ["DATABASE_URL"], open=False, min_size=1, max_size=4)
http = httpx.AsyncClient(timeout=120)
app = FastAPI()
_jwks = {}

SCHEMA = """
CREATE SCHEMA IF NOT EXISTS argus;
CREATE TABLE IF NOT EXISTS argus.audit_intent (
  id uuid PRIMARY KEY,
  ts timestamptz NOT NULL DEFAULT now(),
  tenant text, identity_mode text, subject text, actor text, model text,
  litellm_call_id text, rejected boolean NOT NULL DEFAULT false, reject_reason text, http_status int
);
"""


class Reject(Exception):
    def __init__(self, status, reason, message="invalid or missing credentials"):
        self.status, self.reason, self.message = status, reason, message


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


def error(status, message):
    return JSONResponse({"error": {"message": message, "type": "auth_error" if status == 401 else "invalid_request"}}, status_code=status)


def verify_idp_jwt(token):
    """Validate a JWT from a registered issuer: JWKS per issuer, asymmetric algs only, exact iss/aud, exp required."""
    try:
        iss = jwt.decode(token, options={"verify_signature": False}).get("iss")
        alg = jwt.get_unverified_header(token).get("alg")
    except jwt.PyJWTError:
        raise Reject(401, "malformed_token")
    cfg = REGISTRY["issuers"].get(iss)
    if cfg is None:
        raise Reject(401, "unregistered_issuer")
    if alg not in ASYMMETRIC:
        raise Reject(401, "algorithm_not_allowed")
    client = _jwks.setdefault(iss, PyJWKClient(cfg["jwks_uri"], cache_keys=True, lifespan=600))
    try:
        key = client.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=ASYMMETRIC, audience=cfg["audience"], issuer=iss,
                            options={"require": ["exp", "iss", "aud", "sub"]})
    except jwt.ExpiredSignatureError:
        raise Reject(401, "token_expired")
    except jwt.InvalidAudienceError:
        raise Reject(401, "wrong_audience")
    except jwt.PyJWTError:
        raise Reject(401, "invalid_token")
    return cfg, claims


def principal_from_user_claims(cfg, claims):
    tenant = cfg["users"].get(claims["sub"])
    if tenant is None:
        raise Reject(401, "subject_not_registered")
    return tenant


def verify_delegation(token):
    try:
        c = jwt.decode(token, DELEGATION_SECRET, algorithms=["HS256"], issuer=DELEGATION_ISS, audience="argus-gateway",
                       options={"require": ["exp", "iss", "aud", "sub"]})
    except jwt.ExpiredSignatureError:
        raise Reject(401, "token_expired")
    except jwt.PyJWTError:
        raise Reject(401, "invalid_token")
    return c


def resolve_factory_key(token):
    entry = REGISTRY["factory_keys"].get(hashlib.sha256(token.encode()).hexdigest())
    if not entry:
        return None
    return {"tenant": entry["tenant"], "identity_mode": "factory_key", "subject": entry["subject"], "actor": None,
            "litellm_key": token}


async def resolve(token):
    """Return the principal for a bearer token, or raise Reject."""
    if not token:
        raise Reject(401, "unauthenticated")
    if token.count(".") != 2:
        p = resolve_factory_key(token)
        if p is None:
            raise Reject(401, "unauthenticated")
        return p
    try:
        iss = jwt.decode(token, options={"verify_signature": False}).get("iss")
    except jwt.PyJWTError:
        raise Reject(401, "malformed_token")
    if iss == DELEGATION_ISS:
        c = verify_delegation(token)
        keys = REGISTRY["tenants"][c["tenant"]]
        return {"tenant": c["tenant"], "identity_mode": "delegated_agent", "subject": c["sub"], "actor": c["act"]["sub"],
                "litellm_key": keys["agent_key"]}
    cfg, claims = await anyio.to_thread.run_sync(verify_idp_jwt, token)
    tenant = principal_from_user_claims(cfg, claims)
    return {"tenant": tenant, "identity_mode": "federated_user", "subject": claims["sub"], "actor": None,
            "litellm_key": REGISTRY["tenants"][tenant]["user_key"]}


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.post("/v1/delegate")
async def delegate(request: Request):
    """Fallback for IdP token exchange: validate the user's JWT and the agent's JWT, mint a short-lived token."""
    rid = uuid.uuid4()
    auth = request.headers.get("authorization", "")
    user_tok = auth[7:] if auth.lower().startswith("bearer ") else ""
    agent_tok = request.headers.get("x-agent-token", "")
    principal = None
    try:
        if not user_tok or not agent_tok:
            raise Reject(401, "unauthenticated")
        ucfg, uclaims = await anyio.to_thread.run_sync(verify_idp_jwt, user_tok)
        acfg, aclaims = await anyio.to_thread.run_sync(verify_idp_jwt, agent_tok)
        if acfg is not ucfg:
            raise Reject(401, "issuer_mismatch")
        tenant = principal_from_user_claims(ucfg, uclaims)
        if ucfg["agents"].get(aclaims["sub"]) != tenant:
            raise Reject(401, "agent_not_registered_for_tenant")
        principal = {"tenant": tenant, "identity_mode": "delegation_mint", "subject": uclaims["sub"], "actor": aclaims["sub"]}
    except Reject as r:
        await audit_insert(rid, principal, None, True, r.reason, r.status)
        return error(r.status, r.message)
    now = int(time.time())
    token = jwt.encode({"iss": DELEGATION_ISS, "aud": "argus-gateway", "sub": uclaims["sub"], "act": {"sub": aclaims["sub"]},
                        "tenant": tenant, "iat": now, "exp": now + DELEGATION_TTL}, DELEGATION_SECRET, algorithm="HS256")
    await audit_insert(rid, principal, None, False, None, 200)
    return {"access_token": token, "token_type": "Bearer", "expires_in": DELEGATION_TTL}


@app.api_route("/v1/{path:path}", methods=["GET", "POST"])
async def proxy(path: str, request: Request):
    rid = uuid.uuid4()
    if path not in ("chat/completions", "models"):
        await audit_insert(rid, None, None, True, "path_not_allowed", 404)
        return error(404, "not found")

    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else ""
    try:
        principal = await resolve(token)
    except Reject as r:
        await audit_insert(rid, None, None, True, r.reason, r.status)
        return error(r.status, r.message)
    out_auth = "Bearer " + principal["litellm_key"]

    if request.method == "GET":
        resp = await http.get(f"{LITELLM_URL}/v1/{path}", headers={"authorization": out_auth})
        await audit_insert(rid, principal, None, False, None, resp.status_code)
        return Response(resp.content, resp.status_code, media_type="application/json")

    try:
        body = await request.json()
    except Exception:
        await audit_insert(rid, principal, None, True, "bad_json", 400)
        return error(400, "body must be JSON")
    model = body.get("model")
    if body.get("stream"):
        await audit_insert(rid, principal, model, True, "streaming_unsupported", 400)
        return error(400, "streaming is not supported")

    body.pop("cache_salt", None)  # never client-supplied
    if SALTING_ENABLED:
        body["cache_salt"] = REGISTRY["tenants"][principal["tenant"]]["salt"]
    body["max_tokens"] = min(int(body.get("max_tokens") or MAX_TOKENS_CAP), MAX_TOKENS_CAP)

    await audit_insert(rid, principal, model)
    resp = await http.post(f"{LITELLM_URL}/v1/chat/completions", json=body, headers={"authorization": out_auth})
    # LiteLLM's spend log request_id is the response body id, so that is the join key.
    try:
        call_id = resp.json().get("id")
    except ValueError:
        call_id = None
    await audit_finish(rid, call_id or resp.headers.get("x-litellm-call-id"), resp.status_code)
    passthrough = {k: v for k, v in resp.headers.items() if k.lower() == "x-litellm-response-cost"}
    return Response(resp.content, resp.status_code, media_type="application/json", headers=passthrough)
