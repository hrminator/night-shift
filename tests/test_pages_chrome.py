"""Part 1: shared chrome comes from events and costs, never constants.

The provenance chip and the cost line read the recorded job's own facts:
the date from its first event, the model from its provenance/model_call
events (else the adapter's configured model), the cost from
data/recorded_costs.json. The clock, strip and footer render from code.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main_mod
from app import pages as pages_mod
from app.adapter import MODEL


def test_model_prefers_provenance_then_call_then_adapter():
    prov = [{"kind": "provenance", "payload": {"model": "muse-spark-9.9"}}]
    assert pages_mod.model_for_events(prov) == "muse-spark-9.9"
    call = [{"kind": "model_call", "payload": {"model": "muse-spark-1.3"}}]
    assert pages_mod.model_for_events(call) == "muse-spark-1.3"
    both = call + prov
    assert pages_mod.model_for_events(both) == "muse-spark-9.9"
    assert pages_mod.model_for_events(
        [{"kind": "claim", "payload": {}}]) == MODEL


def test_recorded_chip_carries_date_and_upper_model():
    chip = pages_mod.chip_recorded("2026-10-27", "muse-spark-1.3")
    assert "RECORDED · 2026-10-27 · MUSE-SPARK-1.3" in chip


def test_live_chip_carries_short_copy_id_and_pulse():
    running = pages_mod.chip_live("a1b2c3d4e5f6", running=True)
    assert "LIVE · YOUR COPY #a1b2" in running
    assert "livedot" in running
    done = pages_mod.chip_live("a1b2c3d4e5f6", running=False)
    assert "LIVE · YOUR COPY #a1b2" in done
    assert "livedot" not in done


def test_clock_positions_ticks_and_raises_0047():
    block = pages_mod.clock_block("00:47", amber_dot=True)
    assert block.index("22:30") < block.index("00:38") < \
        block.index("02:00") < block.index("07:00")
    assert '<em class="up">00:47</em>' in block
    assert "dot amber" in block
    assert pages_mod.timeline_pct("21:30") == 0.0
    assert pages_mod.timeline_pct("09:30") == 100.0


def test_strip_escapes_and_tags_code():
    strip = pages_mod.supplier_strip(
        [("the Oslo printer", "Nordtrykk <AS>", "Too slow")])
    assert "Nordtrykk &lt;AS&gt;" in strip
    assert "CODE" in strip


def test_front_door_chrome(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RECORDED_JOB", "6c7c7c742513")
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    body = client.get("/").text
    assert "RECORDED · 2026-10-27 · MUSE-SPARK-1.3" in body
    assert "Night Shift" in body
    assert "the Oslo printer" in body and "the guaranteed van" in body
    assert "Where each line comes from" in body
    assert "Fictional studio and suppliers" in body
    assert "/evidence" in body and "Results in the README" in body
    assert "raw event log" in body
    assert "/static/night.css" in body and "/static/night.js" in body


def test_shared_assets_served():
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    css = client.get("/static/night.css")
    assert css.status_code == 200
    assert ":root" in css.text and "--lamp" in css.text
    js = client.get("/static/night.js")
    assert js.status_code == 200
    assert "Approve this exact text" in js.text
