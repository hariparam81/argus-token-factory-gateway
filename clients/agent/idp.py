"""ZITADEL token helpers for the demo runs (runs on the operator's Mac).

User token: OAuth device authorization flow once (zitadel_login.py), then silent renewal from the stored refresh
token. Agent token: client credentials for the machine user. Secrets live in ~/.argus-secrets, never in the repo.
"""
import base64
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

SECRETS = Path.home() / ".argus-secrets"


def load_env(path):
    env = {}
    for line in Path(path).read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


Z = load_env(SECRETS / "zitadel.env")
BASE = f"https://{Z['ZITADEL_DOMAIN']}"
AUD_SCOPE = f"urn:zitadel:iam:org:project:id:{Z['ZITADEL_PROJECT_ID']}:aud"
REFRESH_FILE = SECRETS / "user_refresh.env"


def post(url, data, headers=None):
    req = urllib.request.Request(url, urllib.parse.urlencode(data).encode(),
                                 {"Content-Type": "application/x-www-form-urlencoded", **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def jwt_claims(token):
    return json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))


def agent_token():
    basic = base64.b64encode(f"{Z['ZITADEL_AGENT_CLIENT_ID']}:{Z['ZITADEL_AGENT_CLIENT_SECRET']}".encode()).decode()
    return post(BASE + "/oauth/v2/token", {"grant_type": "client_credentials", "scope": f"openid {AUD_SCOPE}"},
                {"Authorization": "Basic " + basic})["access_token"]


def user_token():
    refresh = load_env(REFRESH_FILE)["ZITADEL_USER_REFRESH_TOKEN"]
    r = post(BASE + "/oauth/v2/token", {"grant_type": "refresh_token", "refresh_token": refresh,
                                        "client_id": Z["ZITADEL_APP_CLIENT_ID"], "scope": f"openid offline_access {AUD_SCOPE}"})
    if r.get("refresh_token") and r["refresh_token"] != refresh:  # rotated
        save_refresh(r["refresh_token"])
    return r["access_token"]


def save_refresh(token):
    old = os.umask(0o077)
    try:
        REFRESH_FILE.write_text(f"ZITADEL_USER_REFRESH_TOKEN={token}\n")
    finally:
        os.umask(old)
    REFRESH_FILE.chmod(0o600)
