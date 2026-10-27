from fastapi.testclient import TestClient

import app.main as main_mod


def test_front_door_serves_replay_or_empty_state(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    response = client.get("/")
    assert response.status_code == 200
    assert "Night Shift" in response.text


def test_front_door_without_any_record(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RECORDED_JOB", "no-such-job")
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    response = client.get("/")
    assert response.status_code == 200
    assert "No recorded run yet" in response.text
