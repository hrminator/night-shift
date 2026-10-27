"""Evaluation worlds (pure code): 12 cases load, overrides stay in memory."""

from __future__ import annotations

import hashlib
from pathlib import Path

from app import eval_world
from app import runner


def _fixture_hashes() -> dict[str, str]:
    out = {}
    for path in sorted(runner.FIXTURES.iterdir()):
        if path.is_file():
            out[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def test_twelve_cases_load_and_validate(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    cases = eval_world.list_cases()
    assert len(cases) == 12
    by_id = {case["id"]: case for case in cases}
    assert {case["type"] for case in cases} == {
        "decision_only", "complete_job"}
    assert len(by_id) == 12
    decision = [c for c in cases if c["type"] == "decision_only"]
    complete = [c for c in cases if c["type"] == "complete_job"]
    assert len(decision) == 8
    assert len(complete) == 4
    assert {c["id"] for c in complete} == {
        "W1_timely_answer", "W2_no_permission", "W3_late_answer",
        "W4_portal_error"}


def test_nordtrykk_override_applies_in_memory_only(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    before = _fixture_hashes()
    case = eval_world.load_case("alternatives_no_wake")
    with eval_world.patched(case):
        assert "4 working days" in runner.fixture_text("nordtrykk.html")
        assert "10 working days" not in runner.fixture_text("nordtrykk.html")
        assert "10 working days" in (
            runner.FIXTURES / "nordtrykk.html").read_text(encoding="utf-8")
    assert "4 working days" not in runner.fixture_text("nordtrykk.html")
    assert _fixture_hashes() == before


def test_no_permission_brief_carries_no_permission(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    case = eval_world.load_case("W2_no_permission")
    text = eval_world.brief_text_for(case)
    assert "standing permission" not in text.lower()
    assert "waits for my OK on the exact text" in text
    with eval_world.patched(case):
        assert "standing permission" not in runner.fixture_text(
            "brief.md").lower()


def test_decision_facts_merge_in_memory_only(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    case = eval_world.load_case("evidence_must_wake")
    case["overrides"]["decision_facts"] = {"venue_delivery_window": "x"}
    before = _fixture_hashes()
    with eval_world.patched(case):
        assert runner.decision_facts()["venue_delivery_window"] == "x"
    assert _fixture_hashes() == before


def test_arrival_pdf_generated_outside_fixtures(tmp_path):
    case = eval_world.load_case("evidence_no_wake")
    dest = eval_world.revised_pdf_path(case, tmp_path)
    assert Path(dest).parent == tmp_path
    blob = Path(dest).read_bytes()
    assert len(blob) > 500
    assert b"9 November" in blob
    hero = eval_world.revised_pdf_path(
        eval_world.load_case("evidence_must_wake"), tmp_path)
    assert Path(hero) == runner.REVISED_PDF
