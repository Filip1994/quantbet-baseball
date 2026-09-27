import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from quantbot.baseball.db import apply_migrations
from quantbot.baseball.feature_snapshot import FeatureSource, build_feature_snapshot
from quantbot.baseball.feature_snapshot_repository import (
    PostgreSQLFeatureSnapshotRepository,
)
from quantbot.baseball.postgres_repository import EvidenceConflictError

_GAME_ID = "feature-snapshot-pit-016"


def _ensure_fixture(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO fixtures (
                game_id,
                provider,
                provider_game_id,
                home_team_id,
                away_team_id
            )
            VALUES (%s, 'api-sports-baseball', %s, %s, %s)
            ON CONFLICT (game_id) DO NOTHING
            """,
            (_GAME_ID, 990016, 9901, 9902),
        )
    connection.commit()


def _source(
    *,
    observed_at: str,
    retrieved_at: str,
    ref: str,
    checksum_char: str,
) -> FeatureSource:
    return FeatureSource(
        source_name="api-sports-baseball",
        observed_at=observed_at,
        retrieved_at=retrieved_at,
        source_payload_ref=ref,
        source_payload_checksum=checksum_char * 64,
        field_names=("home_win_pct", "away_win_pct"),
    )


def _snapshot(
    *,
    generated_at: str,
    observed_at: str,
    retrieved_at: str,
    ref: str,
    checksum_char: str,
    home_win_pct: float,
):
    return build_feature_snapshot(
        game_id=_GAME_ID,
        feature_version="moneyline-pit-v1",
        generated_at=generated_at,
        kickoff_at="2030-07-04T19:20:00+00:00",
        features={
            "home_win_pct": home_win_pct,
            "away_win_pct": 1.0 - home_win_pct,
        },
        sources=(
            _source(
                observed_at=observed_at,
                retrieved_at=retrieved_at,
                ref=ref,
                checksum_char=checksum_char,
            ),
        ),
    )


def test_feature_snapshot_repository_is_immutable_idempotent_and_point_in_time() -> (
    None
):
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    apply_migrations(Path("."), database_url)

    early = _snapshot(
        generated_at="2030-07-04T15:05:00+00:00",
        observed_at="2030-07-04T14:50:00+00:00",
        retrieved_at="2030-07-04T15:00:00+00:00",
        ref="s3://raw/features-early.json",
        checksum_char="a",
        home_win_pct=0.55,
    )
    late = _snapshot(
        generated_at="2030-07-04T16:05:00+00:00",
        observed_at="2030-07-04T15:40:00+00:00",
        retrieved_at="2030-07-04T16:00:00+00:00",
        ref="s3://raw/features-late.json",
        checksum_char="b",
        home_win_pct=0.58,
    )

    with psycopg.connect(database_url) as connection:
        _ensure_fixture(connection)
        repository = PostgreSQLFeatureSnapshotRepository(connection)

        assert repository.append(early) is True
        assert repository.append(early) is False
        assert repository.append(late) is True

        loaded = repository.get(early.snapshot_id)
        before_any = repository.latest_for_game(
            game_id=_GAME_ID,
            as_of=datetime(2030, 7, 4, 14, 59, tzinfo=UTC),
        )
        between = repository.latest_for_game(
            game_id=_GAME_ID,
            as_of=datetime(2030, 7, 4, 15, 30, tzinfo=UTC),
        )
        after_late = repository.latest_for_game(
            game_id=_GAME_ID,
            as_of=datetime(2030, 7, 4, 16, 30, tzinfo=UTC),
        )

        conflicting = replace(
            early,
            features={"home_win_pct": 0.99, "away_win_pct": 0.01},
        )
        with pytest.raises(EvidenceConflictError, match="conflicting immutable"):
            repository.append(conflicting)

    assert loaded == early
    assert before_any is None
    assert between == early
    assert after_late == late


def test_feature_snapshot_repository_rejects_naive_as_of() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    apply_migrations(Path("."), database_url)

    with psycopg.connect(database_url) as connection:
        repository = PostgreSQLFeatureSnapshotRepository(connection)
        with pytest.raises(ValueError, match="timezone-aware"):
            repository.latest_for_game(
                game_id=_GAME_ID,
                as_of=datetime(2030, 7, 4, 15, 30),  # noqa: DTZ001 - intentional
            )
