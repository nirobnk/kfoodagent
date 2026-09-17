#!/usr/bin/env python3
"""Point Meta's WhatsApp webhook at wherever this machine is reachable right now.

    python3 scripts/set_webhook.py                    # auto-detect the running tunnel
    python3 scripts/set_webhook.py https://xyz.app    # or say it explicitly
    python3 scripts/set_webhook.py --show             # just print what Meta has now

Meta only delivers inbound messages to the callback URL registered on the app,
and a free tunnel gets a new random URL every restart. Whenever that happens the
agent goes silent — outbound still works, so it looks like the agent is broken
when really nothing is arriving. This resets the URL in one command.

Claim a static ngrok domain and none of this is needed twice:
    ngrok config add-authtoken <token>      # dashboard.ngrok.com
    export NGROK_DOMAIN=your-name.ngrok-free.app
    make tunnel && python3 scripts/set_webhook.py

Reads WA_APP_SECRET, WA_ACCESS_TOKEN and WA_VERIFY_TOKEN from .env.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAPH = "https://graph.facebook.com"

# cloudflared and ngrok each publish the current public URL on a local port.
CLOUDFLARED_METRICS = "http://127.0.0.1:20241/quicktunnel"
NGROK_API = "http://127.0.0.1:4040/api/tunnels"


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    path = ROOT / ".env"
    if not path.exists():
        sys.exit("no .env found — copy .env.example and fill it in")
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key] = value.strip().strip('"').strip("'")
    return env


def api(method: str, path: str, **params: str) -> dict:
    url = f"{GRAPH}/{path}"
    data = None
    if method == "GET":
        url += "?" + urllib.parse.urlencode(params)
    else:
        data = urllib.parse.urlencode(params).encode()
    request = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = json.load(error).get("error", {}).get("message", "unknown")
        sys.exit(f"Meta rejected the {method} {path}: {detail}")


def _local_json(url: str) -> dict | None:
    """Read a tunnel's own status endpoint. None if that tunnel is not running."""
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return json.load(response)
    except (OSError, ValueError):
        return None


def detect_tunnel() -> str:
    """The public URL of whichever tunnel is running, or exit with advice."""
    cloudflared = _local_json(CLOUDFLARED_METRICS) or {}
    hostname = cloudflared.get("hostname")
    if hostname:
        return f"https://{hostname}"

    ngrok = _local_json(NGROK_API) or {}
    for tunnel in ngrok.get("tunnels", []):
        if tunnel.get("public_url", "").startswith("https://"):
            return tunnel["public_url"]

    sys.exit(
        "no tunnel found on this machine.\n"
        "  start one first:  make tunnel\n"
        "  or pass the URL:  python3 scripts/set_webhook.py https://your-url"
    )


def reachable(url: str) -> bool:
    """Meta will not accept a callback URL it cannot reach, so check first."""
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=20) as response:
            return response.status == 200
    except (OSError, ValueError):
        return False


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--show"]
    show_only = "--show" in sys.argv

    env = load_env()
    version = env.get("WA_API_VERSION", "v21.0")
    token = env["WA_ACCESS_TOKEN"]

    app_id = env.get("WA_APP_ID") or api(
        "GET", f"{version}/debug_token", input_token=token, access_token=token
    )["data"]["app_id"]
    app_token = f"{app_id}|{env['WA_APP_SECRET']}"

    current = api("GET", f"{version}/{app_id}/subscriptions", access_token=app_token)
    subscription = next(
        (s for s in current.get("data", []) if s.get("object") == "whatsapp_business_account"),
        None,
    )
    if subscription is None:
        sys.exit("this app has no whatsapp_business_account subscription yet — add it in the Meta dashboard once")

    print(f"Meta currently delivers to: {subscription.get('callback_url')}")
    if show_only:
        return

    # Keep every field already subscribed; POSTing a shorter list would silently
    # unsubscribe the rest, and losing "messages" is exactly this bug again.
    fields = sorted(f["name"] for f in subscription.get("fields", []))
    if "messages" not in fields:
        fields.append("messages")

    target = (args[0] if args else detect_tunnel()).rstrip("/").removesuffix("/webhook")

    if not reachable(target):
        sys.exit(f"{target}/health did not answer — is the backend running behind that URL?")

    callback = f"{target}/webhook"
    if callback == subscription.get("callback_url"):
        print("already pointing there, nothing to do")
        return

    api(
        "POST",
        f"{version}/{app_id}/subscriptions",
        object="whatsapp_business_account",
        callback_url=callback,
        verify_token=env["WA_VERIFY_TOKEN"],
        fields=",".join(fields),
        access_token=app_token,
    )
    print(f"now delivering to:          {callback}")
    print(f"fields kept:                {', '.join(fields)}")


if __name__ == "__main__":
    main()
