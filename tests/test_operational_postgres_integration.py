import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest

from quantbot.baseball.db import apply_migrations
from quantbot.baseball.evidence import OddsObservation
from quantbot.baseball.fixture_evidence import FixtureObservation
from quantbot.baseball.operational_acceptance import (
    build_activation_gate_assessment,
    build_budget_projection,
    build_canary_fact,
)
from quantbot.baseball.operational_repository import (
    PostgreSQLOperationalAcceptanceRepository,
)
from quantbot.baseball.postgres_repository import PostgreSQLEvidenceRepository
from quantbot.baseball.runtime_evidence import CollectionCycle


def test_operational_canary_gate_and_performance_views() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    apply_migrations(Path("."), database_url)

    with psycopg.connect(database_url) as connection:
        evidence = PostgreSQLEvidenceRepository(connection)
        operations = PostgreSQLOperationalAcceptanceRepository(connection)

        provider_game_id = 700000 + (uuid.uuid4().int % 100000)
        game_id = str(provider_game_id)
        started = datetime.now(UTC) - timedelta(seconds=2)

        fixture = FixtureObservation(
            fixture_observation_id=str(uuid.uuid4()),
            game_id=game_id,
            provider="api-sports-baseball",
            provider_game_id=provider_game_id,
            league="MLB",
            home_team_id=provider_game_id * 10 + 1,
            home_team_name="Canary Home",
            away_team_id=provider_game_id * 10 + 2,
            away_team_name="Canary Away",
            kickoff_at=(started + timedelta(hours=2)).isoformat(),
            provider_status="NS",
            observed_at=started.isoformat(),
            source_payload_ref=f"s3://raw/canary-{game_id}-fixture.json",
            source_payload_checksum="a" * 64,
            schema_version="1.0",
        )
        assert evidence.append_fixture_observations((fixture,)) == 1

        observation = OddsObservation(
            observation_id=str(uuid.uuid4()),
            game_id=game_id,
            market_family="moneyline",
            line=None,
            selection="home",
            bookmaker="Bet365",
            decimal_odds=2.0,
            raw_price="2.0",
            observed_at=(started + timedelta(milliseconds=100)).isoformat(),
            retrieved_at=(started + timedelta(milliseconds=100)).isoformat(),
            source_payload_ref=f"s3://raw/canary-{game_id}-odds.json",
            source_payload_checksum="b" * 64,
            schema_version="1.0",
            market_status="open",
            kickoff_at=(started + timedelta(hours=2)).isoformat(),
        )
        assert evidence.append_observations((observation,)) == 1

        finished = datetime.now(UTC) + timedelta(seconds=2)
        cycle = CollectionCycle.from_summary(
            cycle_id=str(uuid.uuid4()),
            started_at=started,
            finished_at=finished,
            execution_mode="CANARY",
            summary={
                "status": "collected",
                "games_seen": 1,
                "fixture_observations_inserted": 1,
                "pregame_games": 1,
                "due_events": 1,
                "games_selected": 1,
                "odds_calls": 1,
                "raw_market_rows": 2,
                "canonical_rows": 1,
                "observations_inserted": 1,
                "api_requests": 3,
                "api_remaining": 5,
                "errors": 0,
            },
        )
        assert evidence.append_collection_cycle(cycle) is True

        verified = operations.verify_canary_cycle(cycle.cycle_id)
        assert verified["execution_mode"] == "CANARY"
        assert verified["archive_verified"] is True
        assert verified["db_write_verified"] is True
        assert verified["playable_bookmaker_verified"] is True
        assert verified["playable_observations_inserted"] >= 1

        canary = build_canary_fact(
            cycle_id=cycle.cycle_id,
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            status="PASSED",
            max_api_requests=8,
            api_requests=3,
            fixture_observations_inserted=1,
            observations_inserted=1,
            errors=0,
            archive_verified=True,
            db_write_verified=True,
            reason_codes=(),
        )
        assert operations.append_canary(canary) is True
        passed, latest = operations.canary_passed_recently(
            as_of=finished,
            max_age=timedelta(hours=24),
        )
        assert passed is True
        assert latest == canary

        budget = build_budget_projection(
            daily_request_budget=7500,
            cycle_request_cap=75,
            cron_interval_minutes=15,
            daily_reserve_required=250,
        )
        assessment = build_activation_gate_assessment(
            target="SCHEDULED_COLLECTION",
            assessed_at=finished.isoformat(),
            budget=budget,
            paper_mode=True,
            collection_enabled=False,
            api_key_configured=True,
            raw_archive_configured=True,
            migrations_current=operations.migrations_current(Path(".")),
            runtime_fresh=True,
            canary_passed=True,
            latest_canary_id=canary.canary_id,
        )
        assert assessment.verdict == "READY"
        assert operations.append_assessment(assessment) is True

        performance = operations.performance_snapshot()
        assert performance["settled_picks"] >= 0
        assert performance["clv_available"] >= 0
        assert isinstance(operations.performance_breakdown(), tuple)
