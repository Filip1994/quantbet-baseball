from pathlib import Path

import pytest

from quantbot.baseball import worker
from quantbot.baseball.games_schema_audit import summarize_games


def test_summarize_games_compares_mlb_and_non_mlb_without_inference() -> None:
    rows = [
        {
            "id": 1,
            "date": "2026-09-26T17:00:00+00:00",
            "time": "17:00",
            "timezone": "UTC",
            "week": 1,
            "country": {"id": 1, "name": "USA", "code": "US", "flag": "x"},
            "league": {
                "id": 1,
                "name": "MLB",
                "type": "League",
                "season": 2026,
                "logo": "x",
            },
            "teams": {
                "home": {"id": 10, "name": "Home MLB", "logo": "x"},
                "away": {"id": 11, "name": "Away MLB", "logo": "x"},
            },
            "status": {"long": "Not Started", "short": "NS"},
            "scores": {"home": None, "away": None},
        },
        {
            "id": 2,
            "date": "2026-09-26T09:00:00+00:00",
            "time": "09:00",
            "timezone": "UTC",
            "week": 1,
            "country": {"id": 2, "name": "Japan", "code": "JP", "flag": "x"},
            "league": {
                "id": 2,
                "name": "NPB",
                "type": "League",
                "season": 2026,
                "logo": "x",
            },
            "teams": {
                "home": {"id": 20, "name": "Home NPB", "logo": "x"},
                "away": {"id": 21, "name": "Away NPB", "logo": "x"},
            },
            "status": {"long": "Not Started", "short": "NS"},
            "scores": {"home": None, "away": None},
        },
    ]

    summary = summarize_games(rows)

    assert summary["results_count"] == 2
    assert summary["mlb_present"] is True
    assert summary["non_mlb_league_count"] == 1
    assert (
        summary["mlb_sample"]["top_level_keys"]
        == summary["non_mlb_samples"][0]["top_level_keys"]
    )
    assert not any(summary["mlb_sample"]["optional_fields_present"].values())


def test_worker_runs_armed_games_schema_audit_once_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BASEBALL_ENABLE_COLLECTION", "false")
    monkeypatch.setenv("BASEBALL_ENABLE_CANARY", "false")
    monkeypatch.setenv("BASEBALL_GAMES_SCHEMA_AUDIT_ID", "audit-20260926")
    monkeypatch.setenv("BASEBALL_GAMES_SCHEMA_AUDIT_DATE", "2026-09-26")
    monkeypatch.setattr(worker, "apply_migrations", lambda _root: ())
    monkeypatch.setattr(worker, "_record_activation_gate", lambda *_a, **_k: None)
    monkeypatch.setattr(worker, "_record_runtime", lambda *_a, **_k: None)

    import quantbot.baseball.games_schema_audit as audit_module

    calls = []

    def fake_run(_root: Path, *, audit_id: str, date_iso: str):
        calls.append((audit_id, date_iso))
        return {
            "status": "COMPLETE",
            "games_schema_audit_id": audit_id,
            "provider_requests": 1,
            "results_count": 42,
        }

    monkeypatch.setattr(audit_module, "run_games_schema_audit", fake_run)

    result = worker.run_once(Path("."))

    assert calls == [("audit-20260926", "2026-09-26")]
    assert result["mode"] == "storage-ready"
    assert result["games_schema_audit"]["provider_requests"] == 1
    assert result["collection_enabled"] is False
    assert result["canary_enabled"] is False
