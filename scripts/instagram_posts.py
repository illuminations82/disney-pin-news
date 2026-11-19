#!/usr/bin/env python3
"""Print recent posts from the Instagram accounts in sources.json as JSON.

Uses Meta's Business Discovery API with the token stored in the Keychain by
scripts/instagram_setup.py. Read-only. Used by the 8am roundup job:

    python3.12 scripts/instagram_posts.py [--hours 30]

Output: {"token_days_left": N, "token_extended_by_refresh": bool,
         "accounts": {username: "ok" | error}, "posts": [...]}
Every run also tries to renew the token (kept only if it expires later).
Each post: username, timestamp, permalink, caption, media_type, image.
The token itself is never printed.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

GRAPH = "https://graph.facebook.com/v27.0"
SERVICE = "disney-pin-news-instagram"
ROOT = Path(__file__).resolve().parent.parent


def keychain(account: str) -> str:
    r = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", account, "-w"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def keychain_set(account: str, value: str) -> None:
    subprocess.run(["security", "add-generic-password", "-U", "-s", SERVICE,
                    "-a", account, "-w", value], check=True, capture_output=True)


def get(path: str, params: dict) -> dict:
    url = f"{GRAPH}/{path}?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return {"error": json.loads(e.read()).get("error", {})}
        except Exception:
            return {"error": {"message": f"HTTP {e.code}"}}


def maybe_refresh(token: str, expires: int) -> tuple[str, int]:
    """Try to swap the token for a fresh long-lived one on every run (best effort).

    Keeps the old token if Meta refuses or returns one that expires sooner.
    """
    app_id, secret = keychain("app_id"), keychain("app_secret")
    if not (app_id and secret):
        return token, expires
    res = get("oauth/access_token", {"grant_type": "fb_exchange_token", "client_id": app_id,
                                     "client_secret": secret, "fb_exchange_token": token})
    if "access_token" not in res:
        return token, expires
    new_expires = int(time.time()) + int(res.get("expires_in", 0) or 0)
    if res.get("expires_in") and new_expires > expires:
        keychain_set("user_token", res["access_token"])
        keychain_set("token_expires", str(new_expires))
        return res["access_token"], new_expires
    return token, expires


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=30)
    ap.add_argument("--accounts", nargs="*", help="override the usernames from sources.json")
    args = ap.parse_args()

    token, ig_id = keychain("user_token"), keychain("ig_user_id")
    if not (token and ig_id):
        print(json.dumps({"error": "Instagram not set up: run python3.12 scripts/instagram_setup.py"}))
        return 2
    old_expires = int(keychain("token_expires") or 0)
    token, expires = maybe_refresh(token, old_expires)

    accounts = args.accounts or json.loads((ROOT / "sources.json").read_text()).get("instagram_accounts", [])
    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    fields = ("business_discovery.username({u}){{username,media.limit(25)"
              "{{timestamp,permalink,caption,media_type,media_url,thumbnail_url}}}}")
    out = {"token_days_left": round((expires - time.time()) / 86400, 1),
           "token_extended_by_refresh": expires > old_expires + 3600,
           "accounts": {}, "posts": []}
    for u in accounts:
        res = get(ig_id, {"fields": fields.format(u=u), "access_token": token})
        if "error" in res:
            out["accounts"][u] = res["error"].get("message", "error")[:200]
            continue
        out["accounts"][u] = "ok"
        for m in res.get("business_discovery", {}).get("media", {}).get("data", []):
            ts = datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
            if ts < cutoff:
                continue
            out["posts"].append({
                "username": u,
                "timestamp": ts.isoformat(),
                "permalink": m.get("permalink", ""),
                "caption": (m.get("caption") or "")[:1200],
                "media_type": m.get("media_type", ""),
                "image": m.get("thumbnail_url") or m.get("media_url") or "",
            })
    out["posts"].sort(key=lambda p: p["timestamp"], reverse=True)
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
