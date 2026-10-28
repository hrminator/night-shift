"""Part 3: the comparison line reads k of n from the scorer (pure code).

k counts runs that held without waking; a premature hold never counts in
k. NIGHT_B_RESULTS_DIR pins the folder; otherwise the latest folder with
supervision runs of this case wins.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main_mod
from app import night_b as night_b_mod

PART2_FOLDER = "20261028T205824Z"


def _write_results(folder: Path, records: list[dict],
                   development: bool = True) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "results.json").write_text(
        json.dumps({"development_run": development, "records": records}),
        encoding="utf-8")
    return folder


def _record(case="necessity_no_wake", arm="supervision", holds=0,
            notified=False, premature=0):
    return {"case": case, "arm": arm,
            "observed": {"holds": holds, "notified": notified,
                         "premature_holds": premature}}


def test_counts_hold_without_waking_and_excludes_premature(tmp_path,
                                                           monkeypatch):
    folder = _write_results(tmp_path / "r1", [
        _record(holds=1),
        _record(holds=1, premature=1),
        _record(notified=True),
    ])
    monkeypatch.setenv("NIGHT_B_RESULTS_DIR", str(folder))
    assert night_b_mod.comparison_counts() == {
        "k": 1, "n": 3, "development": True, "folder": "r1"}


def test_other_cases_and_arms_do_not_count(tmp_path, monkeypatch):
    folder = _write_results(tmp_path / "r1", [
        _record(case="W1_timely_answer", holds=1),
        _record(arm="direct", holds=1),
    ])
    monkeypatch.setenv("NIGHT_B_RESULTS_DIR", str(folder))
    assert night_b_mod.comparison_counts() is None
    assert night_b_mod.comparison_line() == ""


def test_final_runs_wording(tmp_path, monkeypatch):
    folder = _write_results(tmp_path / "frozen", [_record(holds=1)],
                            development=False)
    monkeypatch.setenv("NIGHT_B_RESULTS_DIR", str(folder))
    line = night_b_mod.comparison_line()
    assert line.startswith("In our final runs on this exact fixture"
                           " it held without waking in 1 of 1.")
    assert "that is the safe mistake" in line
    assert "never acts without a passing check" in line


def test_unknown_override_reads_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("NIGHT_B_RESULTS_DIR", str(tmp_path / "missing"))
    assert night_b_mod.night_b_results_dir() is None
    assert night_b_mod.comparison_counts() is None


def test_latest_folder_wins_by_default(tmp_path, monkeypatch):
    root = tmp_path / "results"
    (root / "20261027T000000Z").mkdir(parents=True)
    _write_results(root / "20261027T000000Z", [_record(holds=1)])
    _write_results(root / "20261028T000000Z",
                   [_record(holds=1), _record(holds=1)])
    monkeypatch.setattr(night_b_mod, "results_root", lambda: root)
    monkeypatch.delenv("NIGHT_B_RESULTS_DIR", raising=False)
    counts = night_b_mod.comparison_counts()
    assert counts is not None
    assert (counts["k"], counts["n"]) == (2, 2)
    assert counts["folder"] == "20261028T000000Z"


def test_part2_folder_scores_1_of_3():
    folder = night_b_mod.results_root() / PART2_FOLDER
    counts = night_b_mod.comparison_counts(folder)
    assert counts is not None
    assert (counts["k"], counts["n"]) == (1, 3)
    assert counts["development"] is True


def test_front_door_shows_comparison_sentence(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "runs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "runs" / "job-recb00000001.json").write_text(
        json.dumps({"job_id": "recb00000001", "exported": True,
                    "events": [
                        {"id": 1, "job_id": "recb00000001", "seq": 1,
                         "virtual_time": "21:30", "kind": "handoff",
                         "payload": {"variant": "hero"},
                         "created_at": "2026-10-27T12:00:00+00:00"},
                        {"id": 2, "job_id": "recb00000001", "seq": 2,
                         "virtual_time": "00:47", "kind": "question",
                         "payload": {"question": "Can it receive?",
                                     "why_now": "w", "what_checked": "c",
                                     "if_yes": "y", "if_no": "n",
                                     "options": ["Yes", "No"]},
                         "created_at": "2026-10-27T12:04:00+00:00"},
                    ]}),
        encoding="utf-8")
    monkeypatch.setenv("RECORDED_JOB", "recb00000001")
    folder = night_b_mod.results_root() / PART2_FOLDER
    monkeypatch.setenv("NIGHT_B_RESULTS_DIR", str(folder))
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    body = client.get("/").text
    assert "In our development runs on this exact fixture it held" in body
    assert "without waking in 1 of 3" in body
