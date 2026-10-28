"""Send a test push to every live subscription (operator command).

Local (default): sends through app.push.send_to_all, the same code path
as the notify step, against the local DATA_DIR. Prints one status code
per subscription.

Remote (--remote): POSTs to the live app's /owner/phone/test with the
RUN_TOKEN header, so the Thursday test push can be sent from the PC to
the phone subscribed on the deployed site.

Keys and tokens come from the environment and are never printed.

Usage:
  uv run python scripts/send_test_push.py --title "T" --body "B"
  uv run python scripts/send_test_push.py --remote --title "T" --body "B"
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

LIVE_BASE_URL = "https://night-shift-demo.fly.dev"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a test push to every live subscription.")
    parser.add_argument("--title", default="Night Shift test",
                        help="Notification title.")
    parser.add_argument("--body", default=None,
                        help="Notification body (default: test push + UTC).")
    parser.add_argument("--remote", action="store_true",
                        help="Send via the live app's /owner/phone/test.")
    parser.add_argument("--base-url", default=None,
                        help="Remote base URL (default: the live site).")
    return parser.parse_args(argv)


def default_body() -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"Test push at {now}"


def run_local(title: str, body: str) -> int:
    from app import push as push_mod
    from app.store import list_live_push_subscriptions

    if not push_mod.push_configured():
        print("push is disabled or the VAPID keys are missing "
              "(PUSH_ENABLED/VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY)")
        return 1
    live = list_live_push_subscriptions()
    if not live:
        print("no live subscriptions")
        return 1
    results = push_mod.send_to_all(title, body, "/")
    for result in results:
        if result["ok"]:
            print(f"subscription {result['subscription_id']}: "
                  f"HTTP {result['status_code']}")
        else:
            print(f"subscription {result['subscription_id']}: FAILED "
                  f"{result.get('error', '')}")
    return 0


def run_remote(title: str, body: str, base_url: str) -> int:
    import httpx

    token = os.environ.get("RUN_TOKEN", "")
    if not token:
        print("RUN_TOKEN is not set")
        return 1
    url = base_url.rstrip("/") + "/owner/phone/test"
    try:
        response = httpx.post(url, headers={"X-Run-Token": token},
                              json={"title": title, "body": body},
                              timeout=60.0)
    except Exception as exc:  # noqa: BLE001 - operator-facing error
        print(f"remote test push failed: {type(exc).__name__}: {exc}")
        return 1
    print(f"POST {url}: HTTP {response.status_code}")
    if response.status_code == 403:
        print("forbidden: check RUN_TOKEN")
        return 1
    try:
        data = response.json()
    except ValueError:
        print(response.text[:200])
        return 1
    if not data.get("ok"):
        print(f"remote push not sent: {data.get('reason', '?')}")
        return 1
    for result in data.get("results", []):
        if result.get("ok"):
            print(f"subscription {result.get('subscription_id')}: "
                  f"HTTP {result.get('status_code')}")
        else:
            print(f"subscription {result.get('subscription_id')}: FAILED "
                  f"{result.get('error', '')}")
    if not data.get("results"):
        print("no live subscriptions on the remote app")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    title = args.title
    body = args.body if args.body is not None else default_body()
    if args.remote:
        return run_remote(title, body, args.base_url or LIVE_BASE_URL)
    return run_local(title, body)


if __name__ == "__main__":
    raise SystemExit(main())
