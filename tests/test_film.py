"""Part 3: film mode renders the replayed beats from the cue sheet (no browser).

The cue sheet sums to the 2:50 plan; ?film=1 serves all ten beats with the
cues inlined and no forms; ?beat= serves one beat alone; unknown beats 404;
every model word stays word for word from the recorded events.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main_mod
from app import film as film_mod

RECORDED = "6c7c7c742513"
BEATS = ["brief", "read", "verdict", "sheet", "diff", "checks", "decision",
         "note", "dawn", "morning"]


def _export() -> dict:
    path = Path("data/runs") / f"job-{RECORDED}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RECORDED_JOB", RECORDED)
    return TestClient(main_mod.app, raise_server_exceptions=False)


def test_cue_sheet_sums_to_170_seconds():
    cues = film_mod.load_cues()
    assert [entry["name"] for entry in cues["beats"]] == BEATS
    assert all(isinstance(entry["ms"], int) for entry in cues["beats"])
    assert sum(entry["ms"] for entry in cues["beats"]) == 170_000
    assert cues["total_ms"] == 170_000


def test_film_page_serves_all_beats_without_forms(tmp_path, monkeypatch):
    body = _client(tmp_path, monkeypatch).get("/?film=1").text
    assert body.count('class="fbeat"') == 10
    assert 'id="fstage"' in body and 'id="cues"' in body
    assert '"name": "sheet"' in body and '"ms": 20000' in body
    assert "frame-16x9" in body
    assert "RECORDED · 2026-10-27 · MUSE-SPARK-1.3" in body
    assert "<form" not in body
    assert "/visitor/answer" not in body
    assert "Skip to" not in body
    css = Path("static/night.css").read_text(encoding="utf-8")
    assert "body.film,body.film *{cursor:none !important}" in css


def test_film_frame_9x16_and_single_beat(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    vertical = client.get("/?film=1&frame=9x16").text
    assert "frame-9x16" in vertical
    assert vertical.count('class="fbeat"') == 10
    checks = client.get("/?film=1&beat=checks").text
    assert checks.count('class="fbeat"') == 1
    assert 'data-beat="checks"' in checks
    assert client.get("/?film=1&beat=nope").status_code == 404


def test_film_cues_served_for_tooling(tmp_path, monkeypatch):
    response = _client(tmp_path, monkeypatch).get("/film/cues.json")
    assert response.status_code == 200
    assert sum(entry["ms"]
               for entry in response.json()["beats"]) == 170_000


def test_film_model_words_are_verbatim(tmp_path, monkeypatch):
    export = _export()
    body = _client(tmp_path, monkeypatch).get("/?film=1").text
    revised_line = next(
        e["payload"]["quote"] for e in export["events"]
        if e["kind"] == "claim"
        and "leave our warehouse" in e["payload"]["quote"])
    assert revised_line in body
    revised_id = max(e["id"] for e in export["events"]
                     if e["kind"] == "revised_quote")
    notes = [e["payload"]["note"] for e in export["events"]
             if e["kind"] == "check" and e["id"] > revised_id]
    assert len(notes) == 6
    for words in notes:
        assert words in body
    reasons = [e["payload"]["reason"] for e in export["events"]
               if e["kind"] == "decision"]
    for words in reasons:
        assert words in body
    asked = next(e for e in export["events"]
                 if e["kind"] == "question")
    assert asked["payload"]["question"] in body
    for option in asked["payload"]["options"]:
        assert option in body
