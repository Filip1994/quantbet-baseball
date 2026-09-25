from pathlib import Path

import pytest

from quantbot.baseball import db, durable_collector, worker


def test_migration_files_are_sorted(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "010_later.sql").write_text("SELECT 1;", encoding="utf-8")
    (migrations / "001_first.sql").write_text("SELECT 1;", encoding="utf-8")

    assert [path.name for path in db.migration_files(tmp_path)] == [
        "001_first.sql",
        "010_later.sql",
    ]


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        db.database_url_from_env()


def test_worker_is_safe_by_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("BASEBALL_ENABLE_COLLECTION", raising=False)
    monkeypatch.setattr(worker, "apply_migrations", lambda root: ("001.sql",))
    monkeypatch.setattr(worker, "_record_runtime", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker, "_operational_snapshot", lambda *args, **kwargs: None)

    result = worker.run_once(tmp_path)

    assert result["status"] == "ready"
    assert result["mode"] == "storage-ready"
    assert result["collection_enabled"] is False
    assert result["migrations_applied"] == ["001.sql"]


def test_worker_runs_durable_collector_only_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("BASEBALL_ENABLE_COLLECTION", "true")
    monkeypatch.setattr(worker, "apply_migrations", lambda root: ())
    monkeypatch.setattr(worker, "_record_runtime", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker, "_operational_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        durable_collector,
        "collect_durable_once",
        lambda root: {"status": "collected", "observations_inserted": 2},
    )

    result = worker.run_once(tmp_path)

    assert result["mode"] == "collection"
    assert result["collection_enabled"] is True
    assert result["collection"] == {
        "status": "collected",
        "observations_inserted": 2,
    }
