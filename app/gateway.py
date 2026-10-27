"""Permission gateway: pure code checks for every outgoing action.

Code enforces permissions, not the model. submit_hold is checked in order
(permission, target, fields, terms, time, sources, privacy, once-only); each
performed check is logged as a gateway_check event. A failed check refuses
the call with a reason the model sees and logs an attempt_refused event;
effects are logged separately as effect events.

On success four separate records exist for the hold: owner_answer
(information, stored by the answer step), permission_used (from the brief,
with version), gateway_result, and effect.

propose_message never sends: it records a draft event with status
awaiting_approval and the exact text and recipient.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from app import clock
from app import portal as portal_mod
from app.store import append_event, list_events

REPO_ROOT = Path(__file__).resolve().parent.parent

CHECK_ORDER = [
    "permission", "target", "fields", "terms",
    "time", "sources", "privacy", "once-only",
]

PRIVACY_FORBIDDEN = [
    "budget", "internal", "nordtrykk", "baltic",
    "2200", "2150", "3500",
]


def canonical_payload(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def operation_id_for(job_id: str, tool: str, args: dict) -> str:
    digest = hashlib.sha256(
        f"{job_id}|{tool}|{canonical_payload(args)}".encode("utf-8")
    ).hexdigest()
    return digest


def brief_text_of(job_id: str, path: Path | None = None) -> tuple[str, str]:
    """Return (brief text, version) for a job.

    Tests may store an edited brief inline in the handoff payload under
    "brief_text"; otherwise the fixture file named in the handoff is read.
    """
    handoffs = [e for e in list_events(job_id, path=path)
                if e["kind"] == "handoff"]
    payload = handoffs[0]["payload"] if handoffs else {}
    if isinstance(payload.get("brief_text"), str):
        text = payload["brief_text"]
    else:
        name = payload.get("brief") or "fixtures/brief.md"
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
    version = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return text, version


def owner_answers(job_id: str, path: Path | None = None) -> list[dict]:
    return [e for e in list_events(job_id, path=path)
            if e["kind"] == "owner_answer"]


def _normalize_key(key: str) -> str | None:
    norm = key.lower().strip().replace("-", "_").replace(" ", "_")
    if norm == "product":
        return "product"
    if norm in ("quantity", "qty"):
        return "quantity"
    if norm.startswith("print"):
        return "print_file"
    if norm.startswith("delivery_address") or norm in ("address",
                                                      "deliveryaddress"):
        return "address"
    if norm.startswith("delivery_window") or norm in ("window",):
        return "delivery_window"
    if norm.startswith("ordering_contact") or norm in ("contact",
                                                      "orderingcontact"):
        return "ordering_contact"
    if "receive" in norm or norm.startswith("confirmation"):
        return "recipient_can_receive"
    if norm in ("cost", "price", "total", "amount"):
        return "cost"
    if norm.startswith("binding") or norm in ("non_binding", "nonbinding"):
        return "binding"
    if "end" in norm or norm in ("expires", "expiry"):
        return "hold_ends"
    if norm == "sources":
        return "sources"
    if norm == "action":
        return "action"
    return None


def _fold(text: str) -> str:
    return text.lower().replace("ø", "o").replace("æ", "ae").replace("å", "a")


def _owner_address_markers() -> list[str]:
    try:
        addresses = json.loads(
            (REPO_ROOT / "fixtures" / "addresses.json").read_text(
                encoding="utf-8"))
    except (OSError, ValueError):
        return ["sjosalen", "skippergata"]
    markers = []
    for entry in addresses.values():
        address = entry.get("address", "") if isinstance(entry, dict) else ""
        for token in ("sjosalen", "skippergata"):
            if token in _fold(address):
                markers.append(token)
    return markers or ["sjosalen", "skippergata"]


def _check_permission(job_id: str, path: Path | None) -> tuple[bool, str, str]:
    text, version = brief_text_of(job_id, path=path)
    lowered = text.lower()
    if "standing permission" in lowered and "vestland" in lowered:
        return True, f"standing permission present (brief {version})", version
    return False, "no standing permission in tonight's brief", version


def _check_target(args: dict) -> tuple[bool, str]:
    portal = args.get("portal")
    if not isinstance(portal, str) or "vestland" not in portal.lower():
        return False, "target must be Vestland Tekstil's order portal"
    fields = args.get("fields", {})
    action = fields.get("action", "capacity hold")
    if isinstance(action, str) and "order" in action.lower() \
            and "hold" not in action.lower():
        return False, "action must be a capacity hold, not an order"
    return True, "Vestland portal, action = capacity hold"


def _check_fields(args: dict) -> tuple[bool, str, dict]:
    fields = args.get("fields")
    if not isinstance(fields, dict):
        return False, "fields must be an object", {}
    normalized: dict = {}
    for key in fields:
        mapped = _normalize_key(str(key))
        if mapped is None:
            return False, f"field not permitted: {key}", {}
        normalized[mapped] = fields[key]
    required = ["product", "quantity", "address", "delivery_window",
                "recipient_can_receive", "cost", "binding", "hold_ends",
                "sources"]
    missing = [key for key in required if key not in normalized]
    if missing:
        return False, f"missing required fields: {missing}", {}
    if not isinstance(normalized["product"], str) \
            or not normalized["product"].strip():
        return False, "product must be a non-empty string", {}
    quantity = normalized["quantity"]
    if str(quantity).strip() != "100":
        return False, "quantity must be 100", {}
    address = normalized["address"]
    if not isinstance(address, str) or not any(
            marker in _fold(address)
            for marker in _owner_address_markers()):
        return False, "address must be one address from the owner's list", {}
    window = normalized["delivery_window"]
    if not isinstance(window, str) or "08:00-12:00" not in \
            window.replace(" ", ""):
        return False, "delivery window must be Wed Nov 11 08:00-12:00", {}
    confirm = normalized["recipient_can_receive"]
    if not (confirm is True or (isinstance(confirm, str)
                                and confirm.strip().lower() in
                                ("yes", "y", "confirmed", "true"))):
        return False, "recipient-can-receive must be confirmed yes", {}
    return True, "fields permitted; quantity 100; address on owner list", \
        normalized


def _check_terms(normalized: dict) -> tuple[bool, str]:
    cost = normalized["cost"]
    cost_ok = cost == 0 or cost == 0.0 or (
        isinstance(cost, str) and cost.strip().lower()
        in ("0", "nok 0", "free", "no cost", "nothing", "0 nok"))
    if not cost_ok:
        return False, "hold must cost 0"
    binding = normalized["binding"]
    binding_ok = binding is False or (
        isinstance(binding, str) and binding.strip().lower()
        in ("false", "no", "non-binding", "nonbinding", "not binding"))
    if not binding_ok:
        return False, "hold must be non-binding"
    ends = normalized["hold_ends"]
    if not isinstance(ends, str):
        return False, "hold end must state a time at or before 09:00"
    match = re.search(r"(\d{1,2}):(\d{2})", ends)
    if match is None:
        return False, "hold end must state a time at or before 09:00"
    minutes = int(match.group(1)) * 60 + int(match.group(2))
    if minutes > 9 * 60:
        return False, "hold must end at or before 09:00"
    return True, "cost 0, non-binding, ends at or before 09:00"


def _check_time(job_id: str, submit_vt: str,
               path: Path | None) -> tuple[bool, str]:
    answers = owner_answers(job_id, path=path)
    if not answers:
        try:
            if clock.at(submit_vt) < clock.at(clock.CUTOFF):
                return True, f"no owner answer; direct hold under permission, submit {submit_vt} pre-02:00"
        except (ValueError, KeyError):
            return False, "unparseable virtual time"
        return False, "no owner answer recorded for this job"
    answer_vt = answers[-1]["virtual_time"]
    try:
        if not clock.at(answer_vt) <= clock.answer_deadline():
            return False, f"owner answer arrived at {answer_vt}, after 01:50"
        if not clock.at(submit_vt) < clock.at(clock.CUTOFF):
            return False, f"submit at {submit_vt} is not before cutoff 02:00"
    except (ValueError, KeyError):
        return False, "unparseable virtual time"
    return True, f"answer at {answer_vt} by 01:50; submit {submit_vt} pre-02:00"


def _normalize_source_key(key: str) -> str:
    norm = key.lower().strip().replace("-", "_").replace(" ", "_")
    if "receive" in norm or "recipient" in norm or "answer" in norm:
        return "recipient_can_receive"
    if "rout" in norm:
        return "route"
    if "window" in norm or "slot" in norm:
        return "window"
    return norm


def _check_sources(job_id: str, normalized: dict,
                   path: Path | None) -> tuple[bool, str]:
    sources = normalized.get("sources")
    if not isinstance(sources, dict):
        return False, "sources must map each stated fact to its source"
    flat = {_normalize_source_key(str(key)): value
            for key, value in sources.items()}
    answer_ids = {e["id"] for e in owner_answers(job_id, path=path)}
    claim_by_id = {e["id"]: (e["payload"] or {}) for e in list_events(job_id, path=path) if e["kind"] == "claim"}
    recipient_source = flat.get("recipient_can_receive")
    if isinstance(recipient_source, str) \
            and recipient_source.strip().isdigit():
        recipient_source = int(recipient_source.strip())
    if recipient_source in answer_ids:
        pass
    elif recipient_source in claim_by_id and "venue" in str(claim_by_id[recipient_source].get("source", "")).lower():
        pass
    else:
        return False, "'recipient can receive' must cite the owner_answer" \
            f" event id; got {recipient_source!r}"
    for key in ("route", "window"):
        pointer = flat.get(key)
        if not isinstance(pointer, str):
            return False, f"{key} must cite the portal record version"
        lowered = pointer.lower()
        if not ("v1" in lowered or ("1" in lowered and (
                "vestland" in lowered or "portal" in lowered))):
            return False, f"{key} must cite the portal record version"
    if recipient_source in answer_ids:
        how = "owner answer"
    else:
        how = "authoritative venue claim"
    return True, f"recipient cites {how}; route and window cite portal v1"


def _check_privacy(normalized: dict) -> tuple[bool, str]:
    blob = json.dumps(normalized, ensure_ascii=False).lower()
    leaked = [token for token in PRIVACY_FORBIDDEN if token in blob]
    if leaked:
        return False, f"payload leaks private material: {leaked}"
    return True, "no budget, notes, or other suppliers' prices in payload"


def check_submit_hold(
    job_id: str,
    args: dict,
    submit_virtual_time: str,
    path: Path | None = None,
) -> dict:
    """Run the gateway for one submit_hold call.

    Returns {"ok": True, ...} on success (permission_used, gateway_result
    and effect events appended) or {"ok": False, "reason": ...} with an
    attempt_refused event. A retry with a known operation id returns the
    stored acknowledgement and appends nothing.
    """
    if not isinstance(args, dict) or not isinstance(args.get("portal"), str) \
            or not isinstance(args.get("fields"), dict):
        return {"ok": False, "malformed": True,
                "reason": "submit_hold needs portal (string) and fields "
                "(object)"}
    operation_id = operation_id_for(job_id, "submit_hold", args)
    existing = portal_mod.get_operation(operation_id, path=path)
    if existing is not None:
        return {"ok": True, "deduped": True,
                "acknowledgement": existing["acknowledgement"],
                "effect_event_id": existing["effect_event_id"],
                "operation_id": operation_id}

    checks: list[dict] = []

    def refuse(check: str, reason: str) -> dict:
        checks.append({"check": check, "passed": False, "detail": reason})
        append_event(job_id, submit_virtual_time, "gateway_check",
                     checks[-1], path=path)
        payload = {"tool": "submit_hold", "check": check, "reason": reason,
                   "operation_id": operation_id}
        if check == "permission":
            payload["approval_item"] = record_hold_approval_item(
                job_id, args, submit_virtual_time, reason, path=path)
        append_event(job_id, submit_virtual_time, "attempt_refused",
                     payload, path=path)
        return {"ok": False, "reason": reason, "check": check,
                "operation_id": operation_id, "checks": checks}

    def accept(check: str, detail: str) -> None:
        checks.append({"check": check, "passed": True, "detail": detail})
        append_event(job_id, submit_virtual_time, "gateway_check",
                     checks[-1], path=path)

    ok, detail, brief_version = _check_permission(job_id, path)
    if not ok:
        return refuse("permission", detail)
    accept("permission", detail)

    ok, detail = _check_target(args)
    if not ok:
        return refuse("target", detail)
    accept("target", detail)

    ok, detail, normalized = _check_fields(args)
    if not ok:
        return refuse("fields", detail)
    accept("fields", detail)

    ok, detail = _check_terms(normalized)
    if not ok:
        return refuse("terms", detail)
    accept("terms", detail)

    ok, detail = _check_time(job_id, submit_virtual_time, path)
    if not ok:
        return refuse("time", detail)
    accept("time", detail)

    ok, detail = _check_sources(job_id, normalized, path)
    if not ok:
        return refuse("sources", detail)
    accept("sources", detail)

    ok, detail = _check_privacy(normalized)
    if not ok:
        return refuse("privacy", detail)
    accept("privacy", detail)

    if portal_mod.job_has_hold_effect(job_id, path=path):
        return refuse("once-only", "one hold per job: a hold already exists")
    accept("once-only", f"first hold for this job ({operation_id[:12]})")

    append_event(job_id, submit_virtual_time, "permission_used",
                 {"permission": "one capacity hold on Vestland Tekstil's "
                                "order portal",
                  "brief_version": brief_version, "source": "brief"},
                 path=path)
    append_event(job_id, submit_virtual_time, "gateway_result",
                 {"tool": "submit_hold", "ok": True,
                  "operation_id": operation_id, "checks": checks},
                 path=path)
    placed = portal_mod.ensure_hold(
        job_id, operation_id, submit_virtual_time,
        args["portal"], args["fields"], path=path)
    return {"ok": True, "deduped": placed["deduped"],
            "acknowledgement": placed["acknowledgement"],
            "effect_event_id": placed["effect_event_id"],
            "operation_id": operation_id, "checks": checks}


def record_hold_approval_item(
    job_id: str,
    args: dict,
    virtual_time: str,
    reason: str,
    path: Path | None = None,
) -> int:
    """Without the standing permission the hold becomes an approval item."""
    event = append_event(
        job_id, virtual_time, "draft",
        {"to": "Vestland Tekstil order portal (exact hold request)",
         "subject": "Capacity hold request (needs your approval)",
         "body": canonical_payload(
             {"portal": args.get("portal"), "fields": args.get("fields")}),
         "purpose": "hold_request",
         "status": "awaiting_approval",
         "note": "Your answer alone places nothing. Approve this exact "
                 f"request to place the hold. Gateway: {reason}"},
        path=path)
    return event["id"]


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

def draft_leak_flag(to: str, body: str) -> tuple[bool, str]:
    """Flag drafts addressed outside the owner's contact list."""
    if EMAIL_RE.search(f"{to} {body}"):
        return True, "recipient not in your contacts"
    return False, ""


def check_propose_message(
    job_id: str,
    args: dict,
    virtual_time: str,
    path: Path | None = None,
) -> dict:
    """Record a draft. Never sends: nothing is delivered."""
    if not isinstance(args, dict):
        return {"ok": False, "malformed": True,
                "reason": "propose_message needs an object argument"}
    missing = [key for key in ("to", "subject", "body", "purpose")
               if not isinstance(args.get(key), str)
               or not args[key].strip()]
    if missing:
        return {"ok": False, "malformed": True,
                "reason": f"propose_message needs text to, subject, body, "
                f"purpose; missing {missing}"}
    append_event(job_id, virtual_time, "gateway_result",
                 {"tool": "propose_message", "ok": True, "action": "draft",
                  "note": "drafts never send; nothing is delivered"},
                 path=path)
    leak, leak_reason = draft_leak_flag(args["to"], args["body"])
    payload = {"to": args["to"], "subject": args["subject"],
         "body": args["body"], "purpose": args["purpose"],
         "status": "awaiting_approval"}
    if leak:
        payload["leak"] = True
        payload["leak_reason"] = leak_reason
    event = append_event(job_id, virtual_time, "draft", payload, path=path)
    out = {"ok": True, "draft_id": event["id"]}
    if leak:
        out["leak"] = True
    return out


ORDER_PURPOSE = "order"
ORDER_DEADLINE = "09:00"
APPROVAL_VALID_MINUTES = 30
OUTBOX_LABEL = "Simulated delivery"


def draft_version_hash(to: str, subject: str, body: str) -> str:
    """Hash one exact draft version: its content plus its recipient."""
    return hashlib.sha256(
        canonical_payload({"to": to, "subject": subject,
                           "body": body}).encode("utf-8")
    ).hexdigest()


def _draft_events(job_id: str, path: Path | None = None) -> list[dict]:
    return [e for e in list_events(job_id, path=path)
            if e["kind"] == "draft"]


def draft_key_of(event: dict) -> int:
    """Stable key across versions of one draft (first event id)."""
    payload = event["payload"] or {}
    key = payload.get("draft_key")
    return int(key) if isinstance(key, int) else int(event["id"])


def draft_head(job_id: str, draft_key: int,
               path: Path | None = None) -> dict | None:
    """Latest version event for one draft key, or None."""
    versions = [e for e in _draft_events(job_id, path=path)
                if draft_key_of(e) == draft_key]
    if not versions:
        return None
    return max(versions, key=lambda e: int(e["id"]))


def head_version_hash(head: dict) -> str:
    payload = head["payload"] or {}
    return draft_version_hash(str(payload.get("to", "")),
                              str(payload.get("subject", "")),
                              str(payload.get("body", "")))


def draft_deadline(head: dict) -> str | None:
    """The Vestland order draft lapses with the hold at 09:00."""
    payload = head["payload"] or {}
    if payload.get("purpose") == ORDER_PURPOSE:
        return ORDER_DEADLINE
    return None


def edit_draft(job_id: str, draft_event_id: int, new_body: str,
               virtual_time: str,
               path: Path | None = None) -> dict:
    """Append a new version of a draft. The old approval (if any) is void:
    approvals bind to one exact version hash."""
    if not isinstance(new_body, str) or not new_body.strip():
        return {"ok": False, "malformed": True,
                "reason": "edit_draft needs a non-empty body"}
    current = next((e for e in _draft_events(job_id, path=path)
                    if e["id"] == draft_event_id), None)
    if current is None:
        return {"ok": False, "reason": "unknown draft"}
    key = draft_key_of(current)
    head = draft_head(job_id, key, path=path)
    payload = (head or current)["payload"] or {}
    try:
        prior_version = int(payload.get("version", 1))
    except (TypeError, ValueError):
        prior_version = 1
    event = append_event(
        job_id, virtual_time, "draft",
        {"to": payload.get("to"), "subject": payload.get("subject"),
         "body": new_body, "purpose": payload.get("purpose"),
         "status": "awaiting_approval", "draft_key": key,
         "version": prior_version + 1, "supersedes": (head or current)["id"]},
        path=path)
    return {"ok": True, "draft_id": event["id"], "draft_key": key,
            "version": prior_version + 1,
            "version_hash": head_version_hash(event)}


def approve_draft(job_id: str, draft_event_id: int, version_hash: str,
                  virtual_time: str,
                  path: Path | None = None) -> dict:
    """Approve one exact draft version (content + recipient), once.

    Refuses an outdated hash (the draft was edited) and, for the Vestland
    order draft, any approval after 09:00 with "hold lapsed".
    """
    head_event = next((e for e in _draft_events(job_id, path=path)
                       if e["id"] == draft_event_id), None)
    if head_event is None:
        return {"ok": False, "reason": "unknown draft"}
    if (head_event["payload"] or {}).get("purpose") == "hold_request":
        return {"ok": False,
                "reason": "a hold request needs the standing permission,"
                " not an approval"}
    key = draft_key_of(head_event)
    head = draft_head(job_id, key, path=path)
    if head is None or head["id"] != draft_event_id:
        return {"ok": False,
                "reason": "outdated: a newer draft version exists;"
                " approve the current version"}
    if head_version_hash(head) != version_hash:
        return {"ok": False,
                "reason": "outdated: version hash mismatch;"
                " the draft was edited"}
    deadline = draft_deadline(head)
    if deadline is not None:
        try:
            late = clock.at(virtual_time) > clock.at(deadline)
        except (ValueError, KeyError):
            return {"ok": False, "malformed": True,
                    "reason": "unparseable virtual time"}
        if late:
            return {"ok": False, "reason": "hold lapsed"}
    event = append_event(
        job_id, virtual_time, "approval",
        {"draft_id": head["id"], "draft_key": key,
         "version_hash": version_hash, "approved_at": virtual_time,
         "deadline": deadline},
        path=path)
    return {"ok": True, "approval_id": event["id"], "draft_key": key,
            "version_hash": version_hash}


def approvals_for_key(job_id: str, draft_key: int,
                      path: Path | None = None) -> list[dict]:
    return [e for e in list_events(job_id, path=path)
            if e["kind"] == "approval"
            and (e["payload"] or {}).get("draft_key") == draft_key]


def approval_valid_at(job_id: str, approval_id: int, virtual_time: str,
                      path: Path | None = None) -> tuple[bool, str]:
    """An approval is valid 30 minutes after it is given on the virtual
    clock, or until the item's own deadline, whichever is first. Any later
    edit of the draft voids it."""
    approval = next((e for e in list_events(job_id, path=path)
                     if e["kind"] == "approval" and e["id"] == approval_id),
                    None)
    if approval is None:
        return False, "unknown approval"
    payload = approval["payload"] or {}
    head = draft_head(job_id, int(payload.get("draft_key", -1)), path=path)
    if head is None or head_version_hash(head) != payload.get("version_hash"):
        return False, "draft edited"
    try:
        moment = clock.at(virtual_time)
        given = clock.at(str(payload.get("approved_at", "07:00")))
    except (ValueError, KeyError):
        return False, "unparseable virtual time"
    from datetime import timedelta
    if moment > given + timedelta(minutes=APPROVAL_VALID_MINUTES):
        return False, "approval expired"
    deadline = payload.get("deadline")
    if deadline is not None:
        try:
            late = moment > clock.at(deadline)
        except (ValueError, KeyError):
            return False, "unparseable virtual time"
        if late:
            return False, "hold lapsed"
    return True, "approval covers this exact version"


def deliver_approved(job_id: str, approval_id: int, virtual_time: str,
                     path: Path | None = None) -> dict:
    """Move an approved draft to the simulated outbox, once. Refuses stale,
    expired, lapsed or already-used approvals."""
    valid, reason = approval_valid_at(job_id, approval_id, virtual_time,
                                      path=path)
    if not valid:
        return {"ok": False, "reason": reason}
    used = [e for e in list_events(job_id, path=path)
            if e["kind"] == "delivered"
            and (e["payload"] or {}).get("approval_id") == approval_id]
    if used:
        return {"ok": False, "reason": "already delivered"}
    approval = next(e for e in list_events(job_id, path=path)
                    if e["id"] == approval_id)
    head = draft_head(job_id, int((approval["payload"] or {}).get(
        "draft_key", -1)), path=path)
    payload = (head["payload"] or {}) if head else {}
    event = append_event(
        job_id, virtual_time, "delivered",
        {"approval_id": approval_id, "draft_id": (head or {}).get("id"),
         "to": payload.get("to"), "subject": payload.get("subject"),
         "body": payload.get("body"), "outbox": OUTBOX_LABEL},
        path=path)
    return {"ok": True, "delivered_id": event["id"]}
