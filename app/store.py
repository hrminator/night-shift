"""Durable task records: append-only SQLite event log (WAL).

events(id, job_id, seq, virtual_time, kind, payload JSON, created_at UTC)
is written through append_event() only; a trigger refuses UPDATE and DELETE.
jobs(id, status, pending_question_id, current_step, virtual_time, updated_at)
and locks(name, owner, expires_at) are derived state and may be updated.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  virtual_time TEXT NOT NULL,
  kind TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (job_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_events_job_seq ON events (job_id, seq);
DROP TRIGGER IF EXISTS events_no_update;
CREATE TRIGGER events_no_update BEFORE UPDATE ON events
BEGIN
  SELECT RAISE(ABORT, 'events are append-only');
END;
DROP TRIGGER IF EXISTS events_no_delete;
CREATE TRIGGER events_no_delete BEFORE DELETE ON events
BEGIN
  SELECT RAISE(ABORT, 'events are append-only');
END;
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  pending_question_id INTEGER,
  current_step TEXT,
  virtual_time TEXT,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS locks (
  name TEXT PRIMARY KEY,
  owner TEXT,
  expires_at TEXT
);
CREATE TABLE IF NOT EXISTS spend (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  day TEXT NOT NULL,
  job_id TEXT NOT NULL,
  label TEXT NOT NULL,
  input_tokens INTEGER NOT NULL,
  cached_tokens INTEGER NOT NULL,
  output_tokens INTEGER NOT NULL,
  usd REAL NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_spend_day ON spend (day);
CREATE TABLE IF NOT EXISTS operations (
  operation_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  tool TEXT NOT NULL,
  payload TEXT NOT NULL,
  effect_event_id INTEGER,
  acknowledgement TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS push_subscriptions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  endpoint TEXT NOT NULL,
  keys TEXT NOT NULL,
  created_at TEXT NOT NULL,
  label TEXT NOT NULL DEFAULT '',
  dead INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_push_subscriptions_dead
  ON push_subscriptions (dead);
"""


_thread_data_dir = threading.local()


def set_thread_data_dir(path: Path | str) -> None:
    """Pin this thread's database directory (eval concurrency)."""
    _thread_data_dir.value = str(path)


def clear_thread_data_dir() -> None:
    """Drop this thread's pin; fall back to DATA_DIR again."""
    _thread_data_dir.value = None


def db_path() -> Path:
    override = getattr(_thread_data_dir, "value", None)
    base = override or os.environ.get("DATA_DIR", "data")
    return Path(base) / "night_shift.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = path or db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db(path: Path | None = None) -> Path:
    target = path or db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(target)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
    return target


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def create_job(
    job_id: str | None = None,
    status: str = "running",
    current_step: str | None = None,
    virtual_time: str | None = None,
    path: Path | None = None,
) -> dict:
    conn = connect(path)
    try:
        _ensure_init(conn)
        jid = job_id or uuid.uuid4().hex[:12]
        now = _now_utc()
        conn.execute(
            "INSERT INTO jobs (id, status, pending_question_id, current_step,"
            " virtual_time, updated_at) VALUES (?, ?, NULL, ?, ?, ?)",
            (jid, status, current_step, virtual_time, now),
        )
        conn.commit()
        return get_job(jid, path=path)
    finally:
        conn.close()


def get_job(job_id: str, path: Path | None = None) -> dict | None:
    conn = connect(path)
    try:
        _ensure_init(conn)
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def set_job_status(
    job_id: str,
    status: str | None = None,
    pending_question_id: int | None = None,
    clear_pending: bool = False,
    current_step: str | None = None,
    virtual_time: str | None = None,
    path: Path | None = None,
) -> dict | None:
    conn = connect(path)
    try:
        _ensure_init(conn)
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if job is None:
            return None
        new_status = status if status is not None else job["status"]
        if clear_pending:
            new_pending = None
        elif pending_question_id is not None:
            new_pending = pending_question_id
        else:
            new_pending = job["pending_question_id"]
        new_step = current_step if current_step is not None else job["current_step"]
        new_vt = virtual_time if virtual_time is not None else job["virtual_time"]
        conn.execute(
            "UPDATE jobs SET status=?, pending_question_id=?, current_step=?,"
            " virtual_time=?, updated_at=? WHERE id=?",
            (new_status, new_pending, new_step, new_vt, _now_utc(), job_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def append_event(
    job_id: str,
    virtual_time: str,
    kind: str,
    payload: dict | None = None,
    path: Path | None = None,
) -> dict:
    conn = connect(path)
    try:
        _ensure_init(conn)
        if conn.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone() is None:
            raise KeyError(f"unknown job {job_id}")
        row = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) AS m FROM events WHERE job_id=?",
            (job_id,),
        ).fetchone()
        seq = int(row["m"]) + 1
        created = _now_utc()
        body = json.dumps(payload or {}, ensure_ascii=False)
        cur = conn.execute(
            "INSERT INTO events (job_id, seq, virtual_time, kind, payload,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (job_id, seq, virtual_time, kind, body, created),
        )
        conn.execute(
            "UPDATE jobs SET virtual_time=?, updated_at=? WHERE id=?",
            (virtual_time, created, job_id),
        )
        conn.commit()
        return {
            "id": cur.lastrowid,
            "job_id": job_id,
            "seq": seq,
            "virtual_time": virtual_time,
            "kind": kind,
            "payload": payload or {},
            "created_at": created,
        }
    finally:
        conn.close()


def list_jobs(statuses: list[str] | None = None, path: Path | None = None) -> list[dict]:
    """List jobs, optionally filtered to open statuses, oldest first."""
    conn = connect(path)
    try:
        _ensure_init(conn)
        if statuses:
            marks = ",".join("?" for _ in statuses)
            rows = conn.execute(
                f"SELECT * FROM jobs WHERE status IN ({marks})"
                " ORDER BY updated_at ASC",
                tuple(statuses),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY updated_at ASC").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def acquire_lock(name: str, owner: str, ttl_seconds: int = 600,
                 path: Path | None = None) -> bool:
    """Take a named run lock. True when this owner now holds it.

    A lock held by another live owner blocks; an expired lock or one already
    owned by this owner is (re)taken. Locks live in the locks table so two
    processes never run the same job.
    """
    from datetime import timedelta
    conn = connect(path)
    try:
        _ensure_init(conn)
        now = datetime.now(timezone.utc)
        row = conn.execute("SELECT * FROM locks WHERE name = ?",
                           (name,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO locks (name, owner, expires_at)"
                " VALUES (?, ?, ?)",
                (name, owner,
                 (now + timedelta(seconds=ttl_seconds)).isoformat()),
            )
            conn.commit()
            return True
        if row["owner"] == owner:
            conn.execute(
                "UPDATE locks SET expires_at = ? WHERE name = ?",
                ((now + timedelta(seconds=ttl_seconds)).isoformat(), name),
            )
            conn.commit()
            return True
        try:
            expires = datetime.fromisoformat(str(row["expires_at"]))
        except ValueError:
            expires = now
        if expires <= now:
            conn.execute(
                "UPDATE locks SET owner = ?, expires_at = ? WHERE name = ?",
                (owner,
                 (now + timedelta(seconds=ttl_seconds)).isoformat(), name),
            )
            conn.commit()
            return True
        return False
    finally:
        conn.close()


def release_lock(name: str, owner: str,
                 path: Path | None = None) -> bool:
    """Release a lock held by this owner. True when a row was removed."""
    conn = connect(path)
    try:
        _ensure_init(conn)
        cur = conn.execute(
            "DELETE FROM locks WHERE name = ? AND owner = ?", (name, owner))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def record_spend(day: str, job_id: str, label: str, input_tokens: int,
                 cached_tokens: int, output_tokens: int, usd: float,
                 path: Path | None = None) -> dict:
    """Append one model-call spend row. Derived ledger, not an event."""
    conn = connect(path)
    try:
        _ensure_init(conn)
        created = _now_utc()
        cur = conn.execute(
            "INSERT INTO spend (day, job_id, label, input_tokens,"
            " cached_tokens, output_tokens, usd, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (day, job_id, label, input_tokens, cached_tokens,
             output_tokens, usd, created),
        )
        conn.commit()
        return {"id": cur.lastrowid, "day": day, "job_id": job_id,
                "usd": usd}
    finally:
        conn.close()


def day_spend_usd(day: str, path: Path | None = None) -> float:
    """Total recorded model spend for one UTC day, in USD."""
    conn = connect(path)
    try:
        _ensure_init(conn)
        row = conn.execute(
            "SELECT COALESCE(SUM(usd), 0) AS total FROM spend WHERE day = ?",
            (day,),
        ).fetchone()
        return float(row["total"])
    finally:
        conn.close()


def save_push_subscription(endpoint: str, keys: dict, label: str = "",
                           path: Path | None = None) -> dict:
    """Store one owner-phone push subscription. Re-subscribes add rows."""
    conn = connect(path)
    try:
        _ensure_init(conn)
        created = _now_utc()
        body = json.dumps(keys or {}, ensure_ascii=False)
        cur = conn.execute(
            "INSERT INTO push_subscriptions (endpoint, keys, created_at,"
            " label, dead) VALUES (?, ?, ?, ?, 0)",
            (endpoint, body, created, label or ""),
        )
        conn.commit()
        return {"id": cur.lastrowid, "endpoint": endpoint,
                "keys": keys or {}, "created_at": created,
                "label": label or "", "dead": 0}
    finally:
        conn.close()


def list_push_subscriptions(path: Path | None = None) -> list[dict]:
    """Every stored subscription, oldest first, dead ones included."""
    conn = connect(path)
    try:
        _ensure_init(conn)
        rows = conn.execute(
            "SELECT * FROM push_subscriptions ORDER BY id ASC").fetchall()
        out = []
        for row in rows:
            item = dict(row)
            try:
                item["keys"] = json.loads(item["keys"])
            except (ValueError, TypeError):
                item["keys"] = {}
            item["dead"] = int(item.get("dead") or 0)
            out.append(item)
        return out
    finally:
        conn.close()


def list_live_push_subscriptions(path: Path | None = None) -> list[dict]:
    """Subscriptions not marked dead, oldest first."""
    return [s for s in list_push_subscriptions(path=path) if not s["dead"]]


def mark_push_subscription_dead(sub_id: int,
                                path: Path | None = None) -> None:
    """Mark one subscription dead after a 404/410 from the push service."""
    conn = connect(path)
    try:
        _ensure_init(conn)
        conn.execute("UPDATE push_subscriptions SET dead = 1 WHERE id = ?",
                     (sub_id,))
        conn.commit()
    finally:
        conn.close()


def list_events(job_id: str, path: Path | None = None) -> list[dict]:
    conn = connect(path)
    try:
        _ensure_init(conn)
        rows = conn.execute(
            "SELECT * FROM events WHERE job_id=? ORDER BY seq ASC", (job_id,)
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            try:
                item["payload"] = json.loads(item["payload"])
            except (ValueError, TypeError):
                item["payload"] = {}
            out.append(item)
        return out
    finally:
        conn.close()
