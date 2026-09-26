import os
from pathlib import Path

import pytest

from quantbot.baseball.dashboard_app import (
    PLAYABLE_BOOKS,
    build_dashboard_snapshot,
    render_dashboard,
)
from quantbot.baseball.db import apply_migrations


def _snapshot():
    return {
        "generated_at": "2026-09-26T02:00:00+00:00",
        "read_only": True,
        "playable_books": ["bet365", "1xbet"],
        "system": {
            "latest_runtime": {
                "status": "ready",
                "mode": "storage-ready",
                "finished_at": "2026-09-26T01:59:00+00:00",
            },
            "latest_gate": {
                "verdict": "READY",
                "target": "CANARY",
                "reason_codes": [],
                "api_key_configured": True,
                "raw_archive_configured": True,
                "migrations_current": True,
                "paper_mode": True,
                "collection_enabled": False,
                "canary_passed": False,
                "daily_request_budget": 7500,
                "cycle_request_cap": 75,
                "worst_case_daily_requests": 7200,
                "request_headroom": 300,
                "daily_reserve_required": 250,
            },
            "latest_canary": {
                "status": "FAILED",
                "api_requests": 6,
                "max_api_requests": 8,
                "fixture_observations_inserted": 64,
                "observations_inserted": 0,
                "archive_verified": False,
                "db_write_verified": False,
                "reason_codes": ["RAW_ARCHIVE_NOT_VERIFIED"],
            },
            "latest_collection": {
                "execution_mode": "CANARY",
                "status": "collected",
                "games_seen": 64,
                "odds_calls": 4,
                "raw_market_rows": 0,
                "canonical_rows": 0,
                "observations_inserted": 0,
                "errors": 0,
            },
            "evidence": {
                "fixtures": 95,
                "fixture_observations": 260,
                "odds_observations": 0,
                "bookmakers": 0,
                "model_predictions": 0,
                "value_evaluations": 0,
                "final_quote_verifications": 0,
                "registered_picks": 0,
                "settled_picks": 0,
                "result_facts": 0,
                "clv_available": 0,
            },
            "runtime_age_seconds": 60,
            "odds_age_seconds": None,
            "fixture_age_seconds": 60,
            "budget": {
                "daily_request_budget": 7500,
                "cycle_request_cap": 75,
                "worst_case_daily_requests": 7200,
                "request_headroom": 300,
                "daily_reserve_required": 250,
            },
            "budget_safe": True,
        },
        "coverage": {
            "bookmakers": [],
            "playable": [],
            "intelligence_only": [],
            "leagues": [{"league": "MLB", "games": 16, "upcoming": 16}],
        },
        "performance": {
            "performance": {},
            "dashboard": {},
            "breakdown": [],
            "stake_enforced": False,
            "target_stake_rsd": 300,
        },
        "research": {"picks": [], "decisions": []},
    }


def test_render_dashboard_exposes_read_only_control_plane() -> None:
    page = render_dashboard(_snapshot(), tab="overview")

    assert "QuantBet Baseball" in page
    assert "READ ONLY" in page
    assert "Worker heartbeat" in page
    assert "Bet365" not in page
    assert "canary not yet passed" in page


def test_coverage_separates_playable_execution_policy() -> None:
    page = render_dashboard(_snapshot(), tab="coverage")

    assert "Only Bet365 and 1xBet can become paper picks." in page
    assert "INTELLIGENCE ONLY" in page
    assert "No playable quote evidence yet" in page


def test_playable_books_are_exact() -> None:
    assert PLAYABLE_BOOKS == ("bet365", "1xbet")


def test_database_snapshot_is_read_only_against_migrated_schema() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL dashboard integration test")

    apply_migrations(Path("."), database_url)
    snapshot = build_dashboard_snapshot(database_url)

    assert snapshot["read_only"] is True
    assert snapshot["playable_books"] == ["bet365", "1xbet"]
    assert "system" in snapshot
    assert "coverage" in snapshot
    assert "performance" in snapshot
    assert "research" in snapshot
