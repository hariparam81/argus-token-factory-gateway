"""One-time device-flow login for the demo user. Prints a URL and code to approve in a browser,
then stores the refresh token in ~/.argus-secrets/user_refresh.env (mode 600) and prints the user's subject id."""
import json
import time
import urllib.error

import idp

d = idp.post(idp.BASE + "/oauth/v2/device_authorization",
             {"client_id": idp.Z["ZITADEL_APP_CLIENT_ID"], "scope": f"openid offline_access {idp.AUD_SCOPE}"})
print("Open:", d.get("verification_uri_complete") or d["verification_uri"])
print("Code:", d["user_code"], f"(valid {d['expires_in']} s)", flush=True)
deadline = time.time() + d["expires_in"]
while time.time() < deadline:
    time.sleep(d.get("interval", 5))
    try:
        r = idp.post(idp.BASE + "/oauth/v2/token", {"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                                                    "device_code": d["device_code"], "client_id": idp.Z["ZITADEL_APP_CLIENT_ID"]})
    except urllib.error.HTTPError as e:
        err = json.loads(e.read() or b"{}").get("error")
        if err in ("authorization_pending", "slow_down"):
            continue
        raise SystemExit(f"login failed: {err}")
    idp.save_refresh(r["refresh_token"])
    c = idp.jwt_claims(r["access_token"])
    print("logged in. sub =", c["sub"], "| aud =", c["aud"], "| iss =", c["iss"])
    break
else:
    raise SystemExit("code expired")
