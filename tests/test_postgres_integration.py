import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from quantbot.baseball.db import apply_migrations
from quantbot.baseball.evidence import OddsObservation
from quantbot.baseball.fixture_evidence import FixtureObservation
from quantbot.baseball.postgres_repository import PostgreSQLEvidenceRepository
from quantbot.baseball.runtime_evidence import CollectionCycle


def _observation() -> OddsObservation:
    return OddsObservation(
        observation_id=str(uuid.uuid4()),
        game_id="1",
        market_family="moneyline",
        line=None,
        selection="home",
        bookmaker="book-a",
        decimal_odds=2.1,
        raw_price="2.1",
        observed_at="2026-09-20T17:00:00+00:00",
        retrieved_at="2026-09-20T17:00:00+00:00",
        source_payload_ref="s3://raw/payload.json",
        source_payload_checksum="a" * 64,
        schema_version="1.0",
        market_status="open",
        kickoff_at="2026-09-20T19:00:00+00:00",
    )


def test_migrations_and_repository_are_idempotent() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    apply_migrations(Path("."), database_url)
    record = _observation()

    with psycopg.connect(database_url) as connection:
        repository = PostgreSQLEvidenceRepository(connection)
        assert repository.append_observation(record) is True
        assert repository.append_observation(record) is False
        assert repository.get_observation(record.observation_id) == record
        assert repository.stats().observations == 1
        assert (
            repository.latest_observation_times()["1"]
            .isoformat()
            .startswith("2026-09-20T17:00:00")
        )

        fixture = FixtureObservation(
            fixture_observation_id=str(uuid.uuid4()),
            game_id="1",
            provider="api-sports-baseball",
            provider_game_id=1,
            league="MLB",
            home_team_id=101,
            home_team_name="Home Club",
            away_team_id=202,
            away_team_name="Away Club",
            kickoff_at="2026-09-20T19:00:00+00:00",
            provider_status="NS",
            observed_at="2026-09-20T17:00:00+00:00",
            source_payload_ref="s3://raw/games.json",
            source_payload_checksum="b" * 64,
            schema_version="1.0",
        )
        assert repository.append_fixture_observations((fixture,)) == 1
        assert repository.append_fixture_observations((fixture,)) == 0

        started = datetime(2026, 9, 20, 17, 0, tzinfo=UTC)
        cycle = CollectionCycle.from_summary(
            cycle_id=str(uuid.uuid4()),
            started_at=started,
            finished_at=started,
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
                "api_remaining": 75,
                "errors": 0,
            },
        )
        assert repository.append_collection_cycle(cycle) is True
        assert repository.append_collection_cycle(cycle) is False

        repository.append_runtime_cycle(
            run_id=str(uuid.uuid4()),
            started_at=started,
            finished_at=started,
            collection_enabled=False,
            mode="storage-ready",
            status="ready",
            stats={},
        )

        health = repository.health_snapshot()
        assert health["fixture_observations"] == 1
        assert health["distinct_fixtures"] == 1
        assert health["odds_observations"] == 1
        assert health["distinct_quote_games"] == 1
        assert health["bookmakers"] == 1
        assert health["pick_events"] == 0
        assert health["collection_cycles"] == 1
        assert health["runtime_cycles"] == 1
