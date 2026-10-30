"""H1: the pinned exports on the final contract (hero + Night B).

Loads the two job ids the Dockerfile pins and asserts the pin rules:
stored drafts carry no draft marker and none of the misattribution
phrases, and the rendered front door shows the renamed supplier.
"""
import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main_mod
from app import gateway as gateway_mod

ROOT = Path(__file__).resolve().parent.parent
NIGHT_B_FOLDER = "20261030T091757Z"

MISATTRIBUTION_PHRASES = (
    "for confirming",
    "you confirmed",
    "your confirmation",
    "as agreed with you",
)


def _docker_pins():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    hero = re.search(r'RECORDED_JOB="([0-9a-f]+)"', text).group(1)
    night_b = re.search(r'RECORDED_JOB_B="([0-9a-f]+)"', text).group(1)
    return hero, night_b


def _load_export(job_id):
    path = ROOT / "data" / "runs" / f"job-{job_id}.json"
    assert path.exists(), f"pinned export missing: {path.name}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_pinned_drafts_have_no_markers_or_misattribution():
    hero, night_b = _docker_pins()
    for job_id in (hero, night_b):
        record = _load_export(job_id)
        drafts = [e for e in record["events"] if e["kind"] == "draft"]
        assert drafts, job_id
        for draft in drafts:
            subject = draft["payload"].get("subject", "")
            body = draft["payload"].get("body", "")
            assert gateway_mod.find_draft_marker(subject, body) is None, (
                job_id, draft["payload"].get("purpose"))
            blob = f"{subject}\n{body}".lower()
            for phrase in MISATTRIBUTION_PHRASES:
                assert phrase not in blob, (
                    job_id, draft["payload"].get("purpose"), phrase)


def test_front_door_shows_new_supplier_name(tmp_path, monkeypatch):
    hero, _night_b = _docker_pins()
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RECORDED_JOB", hero)
    monkeypatch.setenv("NIGHT_B_RESULTS_DIR", NIGHT_B_FOLDER)
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    for state in ("night", "question", "morning"):
        resp = client.get(f"/?state={state}")
        assert resp.status_code == 200, state
        assert "Rannavere" in resp.text, state
        without_keys = resp.text.replace("baltic_arrival_committed", "")
        assert "baltic" not in without_keys.lower(), state
    question = client.get("/?state=question").text
    assert "held without waking in" in question
