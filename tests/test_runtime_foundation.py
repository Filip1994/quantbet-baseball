from pathlib import Path

import pytest

from quantbot.baseball import (
    db,
    durable_collector,
    mlb_identity_diagnostic,
    official_mlb_enrichment_canary,
    worker,
)


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
    monkeypatch.setattr(
        worker,
        "_record_activation_gate",
        lambda *args, **kwargs: {
            "assessment_id": "assessment-1",
            "target": "CANARY",
            "verdict": "BLOCKED",
            "reason_codes": ["API_KEY_MISSING"],
            "budget": {"cycle_request_cap": 75},
            "checks": {"collection_enabled": False},
        },
    )

    result = worker.run_once(tmp_path)

    assert result["status"] == "ready"
    assert result["mode"] == "storage-ready"
    assert result["collection_enabled"] is False
    assert result["migrations_applied"] == ["001.sql"]
    assert result["activation_gate"] == {
        "assessment_id": "assessment-1",
        "target": "CANARY",
        "verdict": "BLOCKED",
        "reason_codes": ["API_KEY_MISSING"],
        "budget": {"cycle_request_cap": 75},
        "checks": {"collection_enabled": False},
    }


def test_worker_runs_durable_collector_only_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("BASEBALL_ENABLE_COLLECTION", "true")
    monkeypatch.setattr(worker, "apply_migrations", lambda root: ())
    monkeypatch.setattr(worker, "_record_runtime", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        worker,
        "_record_activation_gate",
        lambda *args, **kwargs: pytest.fail(
            "activation gate must not run when collection is enabled"
        ),
    )
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


def test_worker_runs_bounded_mlb_enrichment_canary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("BASEBALL_ENABLE_COLLECTION", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv(
        "BASEBALL_MLB_ENRICHMENT_CANARY_ID",
        "mlb-enrich-canary-1",
    )
    monkeypatch.setenv(
        "BASEBALL_MLB_IDENTITY_MAPPING_VERSION",
        "mlb-2026-v1",
    )
    monkeypatch.setattr(worker, "apply_migrations", lambda root: ())
    monkeypatch.setattr(worker, "_record_runtime", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        durable_collector,
        "collect_durable_once",
        lambda root: {"status": "collected", "api_requests": 0},
    )

    captured = {}

    def fake_canary(database_url, *, mapping_version, now, root):
        captured.update(
            {
                "database_url": database_url,
                "mapping_version": mapping_version,
                "now": now,
                "root": root,
            }
        )
        return {
            "status": "COMPLETE",
            "provider_calls": 1,
            "components_inserted": 7,
            "components_total": 7,
            "point_in_time_eligible": 1,
        }

    monkeypatch.setattr(
        official_mlb_enrichment_canary,
        "run_official_mlb_enrichment_canary",
        fake_canary,
    )

    result = worker.run_once(tmp_path)

    assert result["mode"] == "collection"
    assert result["mlb_enrichment_canary_armed"] is True
    assert result["mlb_enrichment_canary"] == {
        "status": "COMPLETE",
        "provider_calls": 1,
        "components_inserted": 7,
        "components_total": 7,
        "point_in_time_eligible": 1,
        "canary_id": "mlb-enrich-canary-1",
    }
    assert captured["database_url"] == "postgresql://example"
    assert captured["mapping_version"] == "mlb-2026-v1"
    assert captured["now"].tzinfo is not None
    assert captured["root"] == tmp_path


def test_worker_can_run_identity_diagnostic_alongside_collection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("BASEBALL_ENABLE_COLLECTION", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("BASEBALL_MLB_IDENTITY_DIAGNOSTIC_ID", "identity-diag-1")
    monkeypatch.setenv("BASEBALL_MLB_IDENTITY_DATE", "2026-09-26")
    monkeypatch.setenv(
        "BASEBALL_MLB_IDENTITY_MAPPING_VERSION",
        "mlb-2026-v1",
    )
    monkeypatch.setattr(worker, "apply_migrations", lambda root: ())
    monkeypatch.setattr(worker, "_record_runtime", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        durable_collector,
        "collect_durable_once",
        lambda root: {"status": "collected", "api_requests": 0},
    )

    captured = {}

    def fake_diagnostic(database_url, *, date_iso, mapping_version, observed_by, root):
        captured.update(
            {
                "database_url": database_url,
                "date_iso": date_iso,
                "mapping_version": mapping_version,
                "observed_by": observed_by,
                "root": root,
            }
        )
        return {
            "status": "INCOMPLETE",
            "provider_calls": 0,
            "unresolved_fixtures_count": 2,
        }

    monkeypatch.setattr(
        mlb_identity_diagnostic,
        "run_mlb_identity_diagnostic",
        fake_diagnostic,
    )

    result = worker.run_once(tmp_path)

    assert result["mode"] == "collection"
    assert result["mlb_identity_diagnostic_armed"] is True
    assert result["mlb_identity_diagnostic"] == {
        "status": "INCOMPLETE",
        "provider_calls": 0,
        "unresolved_fixtures_count": 2,
        "diagnostic_id": "identity-diag-1",
    }
    assert captured["database_url"] == "postgresql://example"
    assert captured["date_iso"] == "2026-09-26"
    assert captured["mapping_version"] == "mlb-2026-v1"
    assert captured["observed_by"].tzinfo is not None
    assert captured["root"] == tmp_path
