"""Phase 2 federation checks against the public gateway: positive paths plus the negative tests.

Negative cases (all expected 401 and each logged in argus.audit_intent with rejected=true):
no token, wrong audience (test issuer), unregistered issuer, expired token, tampered token, disallowed algorithm,
tenant claimed by header only. The expired-token case needs a token signed by a registered issuer, and the IdP
cannot issue an already-expired token, so a test issuer is registered for the run (JWKS served from a throwaway
container on the internal network) and removed afterwards; its key pair is generated here and never stored.
Env: GATEWAY_URL, TENANT_A_KEY. Writes the test JWKS to the path given as argv[1] and prints test-issuer details.
"""
import base64
import json
import sys
import time
import urllib.error
import urllib.request

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

sys.path.insert(0, __file__.rsplit("/", 1)[0] + "/agent")
import idp  # noqa: E402

TEST_ISS = "https://test-issuer.argus.invalid"
TEST_SUB = "test-subject-expired"


def make_test_key(jwks_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="test-kid", use="sig", alg="RS256")
    open(jwks_path, "w").write(json.dumps({"keys": [jwk]}))
    return key


def http(url, body=None, headers=None):
    req = urllib.request.Request(url, json.dumps(body).encode() if body is not None else None,
                                 {"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def run(gateway, tenant_a_key):
    chat = gateway + "/v1/chat/completions"
    body = {"model": "Qwen/Qwen2.5-Coder-7B-Instruct", "max_tokens": 4, "messages": [{"role": "user", "content": "Say hi"}]}
    bearer = lambda t: {"Authorization": "Bearer " + t}  # noqa: E731
    rows = []

    def case(name, expect, status, detail=""):
        rows.append((name, expect, status, "PASS" if status == expect else "FAIL", detail))

    user = idp.user_token()
    agent = idp.agent_token()
    # positives
    case("federated user call", 200, http(chat, body, bearer(user))[0])
    s, d = http(gateway + "/v1/delegate", {}, {**bearer(user), "X-Agent-Token": agent})
    case("delegation mint (user + agent)", 200, s)
    case("delegated agent call", 200, http(chat, body, bearer(d["access_token"]))[0])
    # negatives
    case("no token", 401, http(chat, body)[0])
    evil = jwt.encode({"iss": "https://evil.example", "aud": idp.Z["ZITADEL_PROJECT_ID"], "sub": "x", "exp": int(time.time()) + 600},
                      "k" * 32, algorithm="HS256")
    case("unregistered issuer", 401, http(chat, body, bearer(evil))[0])
    h, p, sig = user.split(".")
    claims = json.loads(base64.urlsafe_b64decode(p + "=="))
    claims["sub"] = "0"
    tampered = ".".join([h, base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode(), sig])
    case("tampered payload", 401, http(chat, body, bearer(tampered))[0])
    hs = jwt.encode({"iss": claims["iss"], "aud": idp.Z["ZITADEL_PROJECT_ID"], "sub": claims["sub"], "exp": int(time.time()) + 600}, "k" * 32, algorithm="HS256")
    case("disallowed algorithm (HS256 under real issuer)", 401, http(chat, body, bearer(hs))[0])
    case("tenant claimed by header only", 401, http(chat, body, {"X-Tenant": "tenant-b"})[0])
    s, _ = http(chat, body, {**bearer(tenant_a_key), "X-Tenant": "tenant-b"})
    case("tenant A key plus X-Tenant: tenant-b header (header ignored, recorded as tenant-a)", 200, s)
    return rows


def test_issuer_case(gateway, key, aud, exp_offset):
    """Token signed by the registered test issuer. ZITADEL always includes the project in the audience of its own
    tokens and cannot issue an expired one, so wrong-audience and expiry are exercised through this issuer."""
    now = int(time.time())
    t = jwt.encode({"iss": TEST_ISS, "aud": aud, "sub": TEST_SUB, "iat": now - 7200, "exp": now + exp_offset},
                   key, algorithm="RS256", headers={"kid": "test-kid"})
    body = {"model": "Qwen/Qwen2.5-Coder-7B-Instruct", "max_tokens": 4, "messages": [{"role": "user", "content": "hi"}]}
    return http(gateway + "/v1/chat/completions", body, {"Authorization": "Bearer " + t})[0]


def sh(cmd):
    import subprocess
    key = str(__import__("pathlib").Path.home() / ".argus-secrets/droplet_ed25519")
    return subprocess.run(["ssh", "-i", key, "-o", "BatchMode=yes", "root@159.203.59.93", cmd], capture_output=True, text=True, timeout=180)


def main():
    import os
    import subprocess
    gateway, a_key = os.environ["GATEWAY_URL"].rstrip("/"), os.environ["TENANT_A_KEY"]
    key = make_test_key("/tmp/jwks.json")
    kfile = str(__import__("pathlib").Path.home() / ".argus-secrets/droplet_ed25519")
    sh("mkdir -p /tmp/jwks")
    subprocess.run(["scp", "-q", "-i", kfile, "-o", "BatchMode=yes", "/tmp/jwks.json", "root@159.203.59.93:/tmp/jwks/jwks.json"], check=True)
    os.remove("/tmp/jwks.json")
    setup = f"""set -e
docker rm -f jwks-test >/dev/null 2>&1 || true
docker run -d --name jwks-test --network argus --ip 172.28.0.20 -v /tmp/jwks:/srv:ro python:3.12.7-slim python -m http.server 9999 -d /srv >/dev/null
cd /opt/argus/gateway && cp registry.json /tmp/registry.bak && python3 - <<PY
import json
r=json.load(open('registry.json'))
r['issuers']['{TEST_ISS}']={{'jwks_uri':'http://172.28.0.20:9999/jwks.json','audience':'test-aud','users':{{'{TEST_SUB}':'tenant-b'}},'agents':{{}}}}
json.dump(r,open('registry.json','w'),indent=1)
PY
docker compose restart shim >/dev/null 2>&1; sleep 8; echo test issuer registered"""
    print(sh(setup).stdout.strip())
    try:
        rows = run(gateway, a_key)
        for name, aud, off in [("expired token (registered test issuer)", "test-aud", -3600),
                               ("wrong audience (registered test issuer, aud not registered)", "someone-else", 600)]:
            got = test_issuer_case(gateway, key, aud, off)
            rows.append((name, 401, got, "PASS" if got == 401 else "FAIL", ""))
    finally:
        r = sh("cd /opt/argus/gateway && mv /tmp/registry.bak registry.json && docker compose restart shim >/dev/null 2>&1; docker rm -f jwks-test >/dev/null; rm -rf /tmp/jwks; echo test issuer removed")
        print(r.stdout.strip())
    for name, exp, got, res, _ in rows:
        print(f"{res}  {name}: expected {exp}, got {got}")


if __name__ == "__main__":
    main()
