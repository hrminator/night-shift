"""Simulated supplier system: Vestland Tekstil order portal.

Nothing leaves the building. submit_hold records the hold acknowledgement
from SCENARIO.md (hold id H-2041) and inserts the effect row in the same
SQLite transaction as the operation id. A retry with the same operation id
returns the existing record and creates nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.store import _ensure_init, _now_utc, connect

HOLD_ID = "H-2041"


def acknowledgement_text(quantity: int = 100) -> str:
    return (
        f"Vestland Tekstil · Hold {HOLD_ID} · {quantity} tote bags · "
        "production run Fri Nov 6 · van to Sjøsalen, Wed Nov 11, 08:00-12:00 "
        "· Simulated supplier system\n"
        "Hold confirmed until 09:00 · No purchase commitment "
        "· Owner review due 07:00"
    )


def get_operation(
    operation_id: str, path: Path | None = None
) -> dict | None:
    conn = connect(path)
    try:
        _ensure_init(conn)
        row = conn.execute(
            "SELECT * FROM operations WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def job_has_hold_effect(job_id: str, path: Path | None = None) -> bool:
    conn = connect(path)
    try:
        _ensure_init(conn)
        rows = conn.execute(
            "SELECT payload FROM events WHERE job_id = ? AND kind = 'effect'",
            (job_id,),
        ).fetchall()
        for row in rows:
            try:
                payload = json.loads(row["payload"])
            except (ValueError, TypeError):
                continue
            if payload.get("tool") == "submit_hold":
                return True
        return False
    finally:
        conn.close()


def ensure_hold(
    job_id: str,
    operation_id: str,
    virtual_time: str,
    portal: str,
    fields: dict,
    path: Path | None = None,
) -> dict:
    """Insert the effect row and the operation id in one transaction.

    Returns {"deduped": False, "effect_event_id": ..., "acknowledgement": ...}.
    A retry with the same operation id returns the stored record with
    deduped True and inserts nothing.
    """
    conn = connect(path)
    try:
        _ensure_init(conn)
        existing = conn.execute(
            "SELECT * FROM operations WHERE operation_id = ?",
            (operation_id,),
        ).fetchone()
        if existing is not None:
            return {
                "deduped": True,
                "effect_event_id": existing["effect_event_id"],
                "acknowledgement": existing["acknowledgement"],
                "operation_id": operation_id,
            }
        acknowledgement = acknowledgement_text(
            quantity=fields.get("quantity", 100)
            if isinstance(fields.get("quantity"), int) else 100
        )
        row = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) AS m FROM events WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        seq = int(row["m"]) + 1
        created = _now_utc()
        effect_payload = {
            "tool": "submit_hold",
            "operation_id": operation_id,
            "hold_id": HOLD_ID,
            "portal": portal,
            "fields": fields,
            "acknowledgement": acknowledgement,
        }
        cur = conn.execute(
            "INSERT INTO events (job_id, seq, virtual_time, kind, payload,"
            " created_at) VALUES (?, ?, ?, 'effect', ?, ?)",
            (job_id, seq, virtual_time, json.dumps(effect_payload), created),
        )
        effect_event_id = cur.lastrowid
        conn.execute(
            "INSERT INTO operations (operation_id, job_id, tool, payload,"
            " effect_event_id, acknowledgement, created_at)"
            " VALUES (?, ?, 'submit_hold', ?, ?, ?, ?)",
            (operation_id, job_id, json.dumps({"portal": portal,
                                               "fields": fields}),
             effect_event_id, acknowledgement, created),
        )
        conn.execute(
            "UPDATE jobs SET virtual_time = ?, updated_at = ? WHERE id = ?",
            (virtual_time, created, job_id),
        )
        conn.commit()
        return {
            "deduped": False,
            "effect_event_id": effect_event_id,
            "acknowledgement": acknowledgement,
            "operation_id": operation_id,
        }
    finally:
        conn.close()
