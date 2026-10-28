"""The standing permission, parsed once from the brief into a record.

The brief is ours, so parsing may use its fixed phrases. The gateway reads
this record and never the brief text: ``ensure_permission_record`` stores
one ``permission_parsed`` event per job (at job creation for new jobs; on
the first gateway call for older jobs), and every later check reads it.
A brief without the permission box parses to ``action: "none"`` and every
hold is refused with "no permission in brief".
"""

from __future__ import annotations

import hashlib
from pathlib import Path

PERMISSION_ACTION = "reservation_hold"
SUPPLIER = "vestland"
REQUIRED_FACT = "recipient_can_receive"


def parse_permission(brief_text: str) -> dict:
    """Parse the brief's fixed phrases into a permission record."""
    version = hashlib.sha256(brief_text.encode("utf-8")).hexdigest()[:12]
    lowered = brief_text.lower()
    if "standing permission" in lowered and "vestland" in lowered:
        return {
            "action": PERMISSION_ACTION,
            "supplier": SUPPLIER,
            "max_cost": 0,
            "cutoff": "02:00",
            "required_fact": REQUIRED_FACT,
            "version": version,
        }
    return {
        "action": "none",
        "permission": "none",
        "supplier": None,
        "max_cost": None,
        "cutoff": None,
        "required_fact": None,
        "version": version,
    }


def permission_allows(record: dict | None) -> bool:
    """True when the record grants the one reservation hold."""
    return (
        isinstance(record, dict)
        and record.get("action") == PERMISSION_ACTION
        and record.get("permission", PERMISSION_ACTION) != "none"
    )


def get_permission_record(
    job_id: str, path: Path | None = None
) -> dict | None:
    """The job's stored permission record, or None when never parsed."""
    from app.store import list_events

    parsed = [
        e for e in list_events(job_id, path=path)
        if e["kind"] == "permission_parsed"
    ]
    if not parsed:
        return None
    payload = parsed[-1]["payload"] or {}
    return payload if isinstance(payload, dict) else None


def ensure_permission_record(
    job_id: str,
    virtual_time: str = "21:30",
    path: Path | None = None,
) -> dict:
    """Return the stored record, parsing the brief once when missing."""
    from app import gateway as gateway_mod
    from app.store import append_event

    record = get_permission_record(job_id, path=path)
    if record is not None:
        return record
    brief_text, _ = gateway_mod.brief_text_of(job_id, path=path)
    record = parse_permission(brief_text)
    append_event(job_id, virtual_time, "permission_parsed", record,
                 path=path)
    return record


def refusal_reason(record: dict | None) -> str:
    """Why a hold is refused when the record grants nothing."""
    version = (record or {}).get("version", "?")
    return (
        f"no permission in brief {version}: tonight's brief grants no"
        " reservation hold, so the hold needs the owner's approval"
    )


def grant_detail(record: dict) -> str:
    """The fact the permission check asserts when it passes."""
    return (
        f"brief {record.get('version', '?')} permits one"
        f" {record.get('action')} on {record.get('supplier')}, free"
        f" (max cost {record.get('max_cost')}), cutoff"
        f" {record.get('cutoff')}, needs {record.get('required_fact')}"
    )
