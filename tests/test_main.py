from fastapi.testclient import TestClient

import app.main as main_mod


def test_front_door_serves_replay_or_empty_state(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    response = client.get("/")
    assert response.status_code == 200
    assert "Night Shift" in response.text


def test_front_door_shows_recorded_night_cost_by_job_id(tmp_path,
                                                          monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RECORDED_JOB", "6c7c7c742513")
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    response = client.get("/")
    assert response.status_code == 200
    assert ("Recorded night 6c7c7c742513 cost $0.26; 50% of input tokens"
            " served from cache.") in response.text


def test_recorded_cost_line_empty_for_unknown_job():
    assert main_mod.recorded_cost_line("no-such-job") == ""


def test_front_door_without_any_record(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("RECORDED_JOB", "no-such-job")
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    response = client.get("/")
    assert response.status_code == 200
    assert "No recorded run yet" in response.text
