import os
import uuid
from pathlib import Path

import psycopg
import pytest

from quantbot.baseball.db import apply_migrations
from quantbot.baseball.evidence import OddsObservation
from quantbot.baseball.postgres_repository import PostgreSQLEvidenceRepository


def _observation() -> OddsObservation:
    return OddsObservation(
        observation_id=str(uuid.uuid4()),
        game_id="game-1",
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
            repository.latest_observation_times()["game-1"]
            .isoformat()
            .startswith("2026-09-20T17:00:00")
        )
