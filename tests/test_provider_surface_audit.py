from pathlib import Path

import pytest

from quantbot.baseball import provider_surface_audit, worker
from quantbot.baseball.api import BaseballAPIError
from quantbot.baseball.config import BaseballSettings
from quantbot.baseball.raw_archive import ArchiveReceipt


class FakeClient:
    def __init__(self, _settings, *, raw_archive):
        self.raw_archive = raw_archive
        self.request_count = 0

    def get_with_receipt(
        self,
        endpoint,
        params,
        *,
        ttl_seconds=0,
        use_cache=True,
    ):
        del ttl_seconds, use_cache
        self.request_count += 1
        if endpoint == "standings":
            league = params["league"]
            return (
                [{"league": {"id": league}, "position": 1, "form": "WWL"}],
                ArchiveReceipt(
                    ref=f"s3://raw/{endpoint}-{league}.json",
                    checksum="a" * 64,
                    captured_at="2026-09-26T01:00:00+00:00",
                ),
            )
        if endpoint == "teams/statistics" and "id" in params:
            raise BaseballAPIError("wrong parameter contract")
        if endpoint == "teams/statistics":
            return (
                [
                    {
                        "team": {"id": params["team"]},
                        "games": {"played": 100},
                        "runs": {"for": 500, "against": 450},
                    }
                ],
                ArchiveReceipt(
                    ref=f"s3://raw/team-{params['team']}.json",
                    checksum="b" * 64,
                    captured_at="2026-09-26T01:00:00+00:00",
                ),
            )
        if endpoint == "players":
            return (
                [{"id": 999, "name": "Shohei Ohtani"}],
                ArchiveReceipt(
                    ref="s3://raw/player-search.json",
                    checksum="c" * 64,
                    captured_at="2026-09-26T01:00:00+00:00",
                ),
            )
        if endpoint == "players/statistics":
            return (
                [{"player": {"id": params["id"]}, "batting": {"games": 100}}],
                ArchiveReceipt(
                    ref="s3://raw/player-stats.json",
                    checksum="d" * 64,
                    captured_at="2026-09-26T01:00:00+00:00",
                ),
            )
        if endpoint == "odds/bets":
            return (
                [{"id": 1, "name": "Home/Away"}],
                ArchiveReceipt(
                    ref="s3://raw/bets.json",
                    checksum="e" * 64,
                    captured_at="2026-09-26T01:00:00+00:00",
                ),
            )
        if endpoint == "odds/bookmakers":
            return (
                [{"id": 1, "name": "Bet365"}],
                ArchiveReceipt(
                    ref="s3://raw/bookmakers.json",
                    checksum="f" * 64,
                    captured_at="2026-09-26T01:00:00+00:00",
                ),
            )
        raise AssertionError(endpoint)


def test_provider_surface_audit_is_bounded_and_recovers_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_surface_audit, "already_completed", lambda _id: False)
    monkeypatch.setattr(
        provider_surface_audit.BaseballSettings,
        "from_env",
        lambda _root: BaseballSettings(
            api_key="test",
            api_base_url="https://example.invalid",
            api_request_budget=7500,
            api_max_attempts=3,
            api_retry_base_seconds=0.0,
            cache_dir=Path(".cache"),
            raw_archive_dir=Path("."),
            timezone_name="UTC",
            paper_mode=True,
        ),
    )
    monkeypatch.setattr(
        provider_surface_audit,
        "archive_from_env",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(provider_surface_audit, "BaseballAPIClient", FakeClient)

    result = provider_surface_audit.run_provider_surface_audit(
        Path("."),
        audit_id="surface-1",
        season=2026,
    )

    assert result["status"] == "COMPLETE"
    assert result["provider_requests"] == 10
    assert result["request_cap"] == 12
    assert result["results"]["team_stats_mlb_id_contract"]["status"] == "ERROR"
    assert result["results"]["team_stats_mlb_team_contract"]["status"] == "OK"
    assert result["results"]["player_statistics_ohtani"]["status"] == "OK"
    assert result["results"]["odds_bets"]["status"] == "OK"
    assert result["results"]["odds_bookmakers"]["status"] == "OK"


def test_provider_surface_audit_short_circuits_after_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_surface_audit, "already_completed", lambda _id: True)

    result = provider_surface_audit.run_provider_surface_audit(
        Path("."),
        audit_id="surface-1",
        season=2026,
    )

    assert result == {
        "status": "ALREADY_DONE",
        "provider_surface_audit_id": "surface-1",
        "provider_requests": 0,
    }


def test_worker_runs_surface_audit_only_when_storage_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BASEBALL_ENABLE_COLLECTION", "false")
    monkeypatch.setenv("BASEBALL_ENABLE_CANARY", "false")
    monkeypatch.setenv("BASEBALL_PROVIDER_SURFACE_AUDIT_ID", "surface-1")
    monkeypatch.setenv("BASEBALL_PROVIDER_SURFACE_AUDIT_SEASON", "2026")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/db")
    monkeypatch.setattr(worker, "apply_migrations", lambda _root: ())
    monkeypatch.setattr(worker, "_record_activation_gate", lambda *_a, **_k: None)
    monkeypatch.setattr(worker, "_record_runtime", lambda *_a, **_k: None)

    calls = []

    def fake_run(_root, *, audit_id, season):
        calls.append((audit_id, season))
        return {
            "status": "COMPLETE",
            "provider_surface_audit_id": audit_id,
            "provider_requests": 8,
        }

    monkeypatch.setattr(provider_surface_audit, "run_provider_surface_audit", fake_run)

    result = worker.run_once(Path("."))

    assert calls == [("surface-1", 2026)]
    assert result["provider_surface_audit"]["provider_requests"] == 8
    assert result["collection_enabled"] is False
    assert result["canary_enabled"] is False


def test_worker_defaults_empty_optional_surface_audit_season(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BASEBALL_ENABLE_COLLECTION", "false")
    monkeypatch.setenv("BASEBALL_ENABLE_CANARY", "false")
    monkeypatch.setenv("BASEBALL_PROVIDER_SURFACE_AUDIT_ID", "surface-empty-season")
    monkeypatch.setenv("BASEBALL_PROVIDER_SURFACE_AUDIT_SEASON", "")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/db")
    monkeypatch.setattr(worker, "apply_migrations", lambda _root: ())
    monkeypatch.setattr(worker, "_record_activation_gate", lambda *_a, **_k: None)
    monkeypatch.setattr(worker, "_record_runtime", lambda *_a, **_k: None)

    calls = []

    def fake_run(_root, *, audit_id, season):
        calls.append((audit_id, season))
        return {
            "status": "COMPLETE",
            "provider_surface_audit_id": audit_id,
            "provider_requests": 0,
        }

    monkeypatch.setattr(provider_surface_audit, "run_provider_surface_audit", fake_run)

    result = worker.run_once(Path("."))

    assert calls == [("surface-empty-season", 2026)]
    assert result["status"] == "ready"
