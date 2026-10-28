"""The S0 design comps are served as static files under /comps/ (no auth)."""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main_mod

client = TestClient(main_mod.app)

PAGES = {
    "/comps/night-0038.html": [
        "00:38",
        "RECORDED · 2026-10-27 · MUSE-SPARK-1.3",
        "Q-1187-B",
        "Skip to 00:47",
    ],
    "/comps/question-0047.html": [
        "00:47",
        "Muse Spark asks",
        "answer by 01:50",
        "Change one fact instead",
    ],
    "/comps/morning-0700.html": [
        "07:00",
        "Good morning.",
        "HOLD LAPSES 09:00",
        "v·ac7d",
    ],
}


def test_comps_served_without_auth():
    for path, markers in PAGES.items():
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert "text/html" in resp.headers["content-type"], path
        for marker in markers:
            assert marker in resp.text, (path, marker)
