#!/usr/bin/env python3
"""One-time (and every ~60 days) setup for Instagram reads.

Run it yourself in a terminal; it asks for the secrets with hidden input so
they never appear on screen, in shell history, or in a Claude transcript:

    python3.12 scripts/instagram_setup.py

It asks for:
  - the Meta app ID          (App settings > Basic)
  - the Meta app secret      (App settings > Basic > App secret > Show)
  - a short-lived user token (Graph API Explorer > Generate Access Token, with
    instagram_basic, instagram_manage_insights, pages_read_engagement,
    pages_show_list, business_management)

It swaps the short-lived token for a ~60-day token, finds your Instagram
professional account, and stores everything in the macOS login Keychain under
the service name "disney-pin-news-instagram". Nothing is written to the repo.
"""
from __future__ import annotations

import getpass
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request

GRAPH = "https://graph.facebook.com/v27.0"
SERVICE = "disney-pin-news-instagram"


def get(url: str, params: dict) -> dict:
    with urllib.request.urlopen(url + "?" + urllib.parse.urlencode(params), timeout=30) as r:
        return json.load(r)


def keychain_set(account: str, value: str) -> None:
    # -U updates an existing item. The secret goes in via argv to `security`,
    # which is local to this machine and not logged anywhere.
    subprocess.run(["security", "add-generic-password", "-U", "-s", SERVICE,
                    "-a", account, "-w", value], check=True)


def main() -> int:
    app_id = input("Meta app ID: ").strip()
    app_secret = getpass.getpass("Meta app secret (hidden): ").strip()
    short = getpass.getpass("Short-lived user token from Graph API Explorer (hidden): ").strip()
    if not (app_id and app_secret and short):
        print("All three values are required.")
        return 1

    try:
        res = get(f"{GRAPH}/oauth/access_token", {
            "grant_type": "fb_exchange_token", "client_id": app_id,
            "client_secret": app_secret, "fb_exchange_token": short})
    except urllib.error.HTTPError as e:
        print("Token exchange failed:", e.read().decode()[:400])
        return 1
    token = res["access_token"]
    expires = int(time.time()) + int(res.get("expires_in", 60 * 24 * 3600))

    pages = get(f"{GRAPH}/me/accounts",
                {"fields": "name,instagram_business_account{id,username}", "access_token": token})
    ig = next((p["instagram_business_account"] for p in pages.get("data", [])
               if p.get("instagram_business_account")), None)
    if not ig:
        print("No Instagram professional account found on your Pages. "
              "Make sure you ticked the Page and Instagram account when generating the token.")
        return 1

    keychain_set("app_id", app_id)
    keychain_set("app_secret", app_secret)
    keychain_set("user_token", token)
    keychain_set("token_expires", str(expires))
    keychain_set("ig_user_id", ig["id"])
    days = (expires - time.time()) / 86400
    print(f"Saved. Instagram account @{ig['username']} (id {ig['id']}); token valid ~{days:.0f} days.")
    print("Test it with:  python3.12 scripts/instagram_posts.py --hours 72")
    return 0


if __name__ == "__main__":
    sys.exit(main())
