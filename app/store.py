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
"""


def db_path() -> Path:
    return Path(os.environ.get("DATA_DIR", "data")) / "night_shift.db"


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
