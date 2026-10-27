"""Seeding test: empty DATA_DIR gets the bundled run records on startup."""

from __future__ import annotations

import json

from app.main import bundled_runs_dir, seed_bundled_runs


def test_seed_copies_bundled_records_into_empty_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert bundled_runs_dir().glob("read-sources-*.json")
    copied = seed_bundled_runs()
    assert copied, "expected bundled records to be seeded"
    seeded = sorted((tmp_path / "runs").glob("read-sources-*.json"))
    assert seeded, "expected read-sources-*.json in DATA_DIR/runs"
    for path in seeded:
        expected = bundled_runs_dir() / path.name
        assert expected.is_file()
        assert json.loads(path.read_text(encoding="utf-8")) == json.loads(
            expected.read_text(encoding="utf-8")
        )


def test_seed_never_overwrites_existing_files(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    runs = tmp_path / "runs"
    runs.mkdir(parents=True)
    sentinel = runs / "read-sources-20261027T104733Z.json"
    sentinel.write_text('{"sentinel": true}', encoding="utf-8")
    assert seed_bundled_runs() == []
    assert sentinel.read_text(encoding="utf-8") == '{"sentinel": true}'
