"""Real Web Push delivery for the owner's own job only.

The night's notify step (the model's accepted ask_owner) may deliver one
real push per stored phone subscription, but only when the job is the
operator's own job (owner_job), PUSH_ENABLED is on, and VAPID keys are
configured. Visitor copies and eval runs never push: they keep the
simulated question event exactly as before.

Config comes from the environment and key values are never logged:
VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT (a mailto: or https:
URL, default mailto:owner@example.invalid), PUSH_ENABLED (default off).
"""

from __future__ import annotations

import json
import os

DEFAULT_SUBJECT = "mailto:owner@example.invalid"
PUSH_TIMEOUT_SECONDS = 10
PUSH_TTL_SECONDS = 3600

#: Test seam: when set, send_one delegates to this callable instead of the
#: network. It takes (subscription, payload) and returns {"status_code": int}
#: or raises PushError. Tests use a fake; production uses pywebpush.
SEND_PUSH_FN = None


def push_enabled() -> bool:
    """True only when the operator has switched push on."""
    return os.environ.get("PUSH_ENABLED", "").strip().lower() in (
        "1", "true", "yes", "on")


def vapid_public_key() -> str:
    """The VAPID public key (base64url, safe to serve to the phone page)."""
    return os.environ.get("VAPID_PUBLIC_KEY", "").strip()


def vapid_subject() -> str:
    """The VAPID subject claim; a mailto: or https: URL."""
    return os.environ.get("VAPID_SUBJECT", "").strip() or DEFAULT_SUBJECT


def _vapid_private_key() -> str:
    return os.environ.get("VAPID_PRIVATE_KEY", "").strip()


def push_configured() -> bool:
    """True when push is on and both VAPID keys are present."""
    return bool(
        push_enabled() and vapid_public_key() and _vapid_private_key())


class PushError(Exception):
    """One push delivery failed. status is the HTTP status, if any."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def send_one(subscription: dict, payload: dict) -> dict:
    """Send one push through pywebpush. Returns {"status_code": int}.

    Raises PushError on any failure; a dead endpoint surfaces as status
    404 or 410. Key values never appear in errors.
    """
    if SEND_PUSH_FN is not None:
        return SEND_PUSH_FN(subscription, payload)
    from pywebpush import WebPushException, webpush

    try:
        response = webpush(
            subscription_info={
                "endpoint": subscription["endpoint"],
                "keys": subscription["keys"],
            },
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=_vapid_private_key(),
            vapid_claims={"sub": vapid_subject()},
            ttl=PUSH_TTL_SECONDS,
            timeout=PUSH_TIMEOUT_SECONDS,
        )
    except WebPushException as exc:
        raise PushError(_short_error(exc), status=exc.status_code) from exc
    except Exception as exc:  # noqa: BLE001 - every failure is a PushError
        raise PushError(f"{type(exc).__name__}: {exc}"[:200]) from exc
    return {"status_code": int(response.status_code)}


def _short_error(exc: Exception) -> str:
    text = str(exc)
    if len(text) > 200:
        text = text[:200]
    return text or type(exc).__name__


def send_to_all(title: str, body: str, url: str) -> list[dict]:
    """Send one push per live subscription; mark 404/410 dead.

    This is the one shared code path: the notify step, the test endpoint
    and the operator script all send through here. Returns one result per
    subscription: {"subscription_id", "ok", "status_code"/"error",
    "seconds"}. A delivery failure is a result, never an exception.
    """
    import time

    from app.store import (list_live_push_subscriptions,
                           mark_push_subscription_dead)

    results: list[dict] = []
    for sub in list_live_push_subscriptions():
        started = time.monotonic()
        try:
            outcome = send_one(
                {"endpoint": sub["endpoint"], "keys": sub["keys"]},
                {"title": title, "body": body, "url": url},
            )
            results.append({
                "subscription_id": sub["id"], "ok": True,
                "status_code": outcome["status_code"],
                "seconds": round(time.monotonic() - started, 3),
            })
        except PushError as exc:
            if exc.status in (404, 410):
                try:
                    mark_push_subscription_dead(sub["id"])
                except Exception:  # noqa: BLE001 - delivery already failed
                    pass
            results.append({
                "subscription_id": sub["id"], "ok": False,
                "error": str(exc)[:200], "status": exc.status,
                "seconds": round(time.monotonic() - started, 3),
            })
        except Exception as exc:  # noqa: BLE001 - a result, not a crash
            results.append({
                "subscription_id": sub["id"], "ok": False,
                "error": f"{type(exc).__name__}: {exc}"[:200],
                "status": None,
                "seconds": round(time.monotonic() - started, 3),
            })
    return results
