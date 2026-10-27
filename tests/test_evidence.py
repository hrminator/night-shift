"""Evidence page tests: render /evidence from a fixture record via the view."""

import json

import app.main as main_mod
from app.main import evidence


def _write_record(directory, record):
    runs = directory / "runs"
    runs.mkdir()
    (runs / "read-sources-20261027T104733Z.json").write_text(
        json.dumps(record), encoding="utf-8"
    )


RECORD = {
    "model_reported": "muse-spark-1.3",
    "run_at_utc": "2026-10-27T10:47:16+00:00",
    "effort": "low",
    "calls": [
        {
            "name": "first",
            "seconds": 7.5,
            "input_tokens": 6349,
            "output_tokens": 926,
            "reasoning_tokens": 646,
            "effort": "low",
            "status": "completed",
        },
        {
            "name": "replay",
            "seconds": 0.99,
            "input_tokens": 1760,
            "output_tokens": 32,
            "reasoning_tokens": 20,
            "effort": "low",
            "status": "completed",
        },
    ],
    "replay_input_tokens": 1760,
    "first_call_input_tokens": 6349,
    "claims": [
        {
            "source": "baltic_quote_Q-1187-B.pdf",
            "version": None,
            "file_id": "file-1324930856329706",
            "quote": "Delivery: Goods will leave our warehouse by 10 November.",
        },
        {
            "source": "vestland_portal.json",
            "version": "1",
            "file_id": None,
            "quote": "Wed Nov 11 08:00-12:00",
        },
    ],
}


def test_evidence_renders_fixture_record(tmp_path, monkeypatch):
    _write_record(tmp_path, RECORD)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    body = evidence()
    assert isinstance(body, str)
    assert "real muse-spark-1.3 result" in body
    assert "2026-10-27" in body
    assert "baltic_quote_Q-1187-B.pdf" in body
    assert "vestland_portal.json" in body
    assert "Delivery: Goods will leave our warehouse by 10 November." in body
    assert "<blockquote>" in body
    assert "scan-styled PDF (image only, no text layer)" in body
    assert "7.5" in body and "6349" in body
    assert "Replay turn billed 1760 input tokens vs 6349 on the first call" in body


def test_evidence_empty_runs_dir_is_404(tmp_path, monkeypatch):
    (tmp_path / "runs").mkdir()
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    response = main_mod.evidence()
    assert response.status_code == 404
