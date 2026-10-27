"""Seeding + recorded-replay fallback (pure code, no model).

The volume starts empty on Fly: startup seeds every bundled file under
data/runs into DATA_DIR/runs without ever overwriting, and the recorded
replay falls back to the baked-in data/runs for any file the volume lacks.
"""

from __future__ import annotations

from app.main import bundled_runs_dir, seed_bundled_runs
from app import replay as replay_mod


def _bundled_files() -> list:
    return sorted(p for p in bundled_runs_dir().glob("*") if p.is_file())


def test_seed_copies_every_bundled_file_into_empty_data_dir(
        tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert any(p.name.startswith("job-") for p in _bundled_files())
    copied = seed_bundled_runs()
    assert copied, "expected bundled records to be seeded"
    for bundled in _bundled_files():
        seeded = tmp_path / "runs" / bundled.name
        assert seeded.is_file(), bundled.name
        assert seeded.read_bytes() == bundled.read_bytes()


def test_seed_never_overwrites_existing_files(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    runs = tmp_path / "runs"
    runs.mkdir(parents=True)
    sentinel = runs / "read-sources-20261027T104733Z.json"
    sentinel.write_text('{"sentinel": true}', encoding="utf-8")
    copied = seed_bundled_runs()
    assert sentinel.read_text(encoding="utf-8") == '{"sentinel": true}'
    assert sentinel not in copied
    assert any(p.name.startswith("job-") for p in copied)


def test_seed_second_run_copies_nothing_new(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert seed_bundled_runs(), "first seed should copy"
    assert seed_bundled_runs() == [], "second seed should find all present"


def test_recorded_replay_falls_back_to_bundled(tmp_path, monkeypatch):
    """Empty volume: the default replay still finds a bundled hero run."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("RECORDED_JOB", raising=False)
    resolved = replay_mod.resolve_recorded_job()
    assert resolved is not None
    assert resolved["path"].parent == bundled_runs_dir()


def test_recorded_job_name_falls_back_to_bundled(tmp_path, monkeypatch):
    """A RECORDED_JOB missing from the volume resolves from bundled data."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    hero = next(p for p in _bundled_files() if p.name.startswith("job-"))
    want = hero.stem.removeprefix("job-")
    monkeypatch.setenv("RECORDED_JOB", want)
    resolved = replay_mod.resolve_recorded_job()
    assert resolved is not None
    assert resolved["path"] == hero


def test_live_run_file_wins_over_bundled(tmp_path, monkeypatch):
    """When the volume holds the file, the live copy is the replay source."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("RECORDED_JOB", raising=False)
    hero = next(p for p in _bundled_files() if p.name.startswith("job-"))
    live = tmp_path / "runs" / hero.name
    live.parent.mkdir(parents=True, exist_ok=True)
    live.write_bytes(hero.read_bytes())
    assert replay_mod.find_run_file(hero.stem) == live
    assert replay_mod.find_run_file("no-such-run") is None
