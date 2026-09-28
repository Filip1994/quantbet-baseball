import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from quantbot.baseball.db import apply_migrations
from quantbot.baseball.game_history import GameHistorySnapshot, canonical_game_history
from quantbot.baseball.game_history_repository import PostgreSQLGameHistoryRepository
from quantbot.baseball.postgres_repository import PostgreSQLEvidenceRepository
from quantbot.baseball.raw_archive import ArchiveReceipt


def _snapshot():
    rows = [
        {
            "id": 185629,
            "date": "2026-09-08T00:10:00+00:00",
            "timezone": "UTC",
            "status": {"long": "Finished", "short": "FT"},
            "league": {"id": 1, "season": 2026},
            "teams": {
                "home": {"id": 31, "name": "San Francisco Giants"},
                "away": {"id": 33, "name": "St.Louis Cardinals"},
            },
            "scores": {
                "home": {
                    "hits": 10,
                    "errors": 0,
                    "innings": {"1": 1, "9": 0, "extra": 2},
                    "total": 5,
                },
                "away": {
                    "hits": 9,
                    "errors": 1,
                    "innings": {"1": 0, "9": 1, "extra": 1},
                    "total": 4,
                },
            },
        }
    ]
    return canonical_game_history(
        rows,
        ArchiveReceipt(
            ref="s3://raw/season-history.json",
            checksum="a" * 64,
            captured_at="2026-09-26T08:00:00+00:00",
        ),
        league_id=1,
        season=2026,
    )[0]


def test_game_history_repository_is_idempotent_and_point_in_time_queryable() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")

    apply_migrations(Path("."), database_url)
    snapshot = _snapshot()

    with psycopg.connect(database_url) as connection:
        repository = PostgreSQLGameHistoryRepository(connection)
        assert repository.append_snapshot(snapshot) is True
        assert repository.append_snapshot(snapshot) is False

        records = repository.latest_snapshots_for_team_before(
            team_id=31,
            league_id=1,
            season=2026,
            scheduled_before=datetime(2026, 9, 9, 0, 0, tzinfo=UTC),
            observed_by=datetime(2026, 9, 26, 9, 0, tzinfo=UTC),
        )
        counts = repository.counts()

    assert len(records) == 1
    assert records[0].provider_game_id == 185629
    assert records[0].went_extra_innings is True
    assert counts["snapshots"] >= 1
    assert counts["distinct_games"] >= 1


def _health_test_snapshot(
    *, provider_game_id: int, extra: int | None
) -> GameHistorySnapshot:
    return GameHistorySnapshot(
        snapshot_id=str(uuid.uuid4()),
        provider="api-sports-baseball",
        provider_game_id=provider_game_id,
        observed_at="2026-09-26T18:00:00+00:00",
        scheduled_first_pitch="2026-09-25T23:00:00+00:00",
        provider_timezone="UTC",
        status_long="Finished",
        status_short="FT",
        league_id=1,
        season=2026,
        home_team_id=901,
        home_team_name="Health Test Home",
        away_team_id=902,
        away_team_name="Health Test Away",
        home_score=4,
        away_score=3,
        home_hits=8,
        away_hits=7,
        home_errors=0,
        away_errors=0,
        home_innings={"1": 1, "9": 0, "extra": extra},
        away_innings={"1": 0, "9": 0, "extra": extra},
        source_payload_ref=f"s3://raw/health-test-{provider_game_id}.json",
        source_payload_checksum="b" * 64,
    )


def test_health_counts_only_non_null_extra_inning_values() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")

    apply_migrations(Path("."), database_url)
    regular = _health_test_snapshot(provider_game_id=990000001, extra=None)
    extra = _health_test_snapshot(provider_game_id=990000002, extra=0)

    with psycopg.connect(database_url) as connection:
        history = PostgreSQLGameHistoryRepository(connection)
        evidence = PostgreSQLEvidenceRepository(connection)
        before = evidence.health_snapshot()["game_history_extra_inning_games"]

        try:
            assert history.append_snapshot(regular) is True
            assert history.append_snapshot(extra) is True
            after = evidence.health_snapshot()["game_history_extra_inning_games"]
            assert after == before + 1
        finally:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM api_sports_game_history_snapshots "
                    "WHERE snapshot_id IN (%s, %s)",
                    (regular.snapshot_id, extra.snapshot_id),
                )
            connection.commit()

def test_season_reconstruction_read_uses_latest_archived_snapshot_per_game() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")

    apply_migrations(Path("."), database_url)
    old = GameHistorySnapshot(
        snapshot_id=str(uuid.uuid4()),
        provider="api-sports-baseball",
        provider_game_id=990000101,
        observed_at="2026-09-26T10:00:00+00:00",
        scheduled_first_pitch="2026-09-20T18:00:00+00:00",
        provider_timezone="UTC",
        status_long="Finished",
        status_short="FT",
        league_id=1,
        season=2026,
        home_team_id=903,
        home_team_name="Research Home",
        away_team_id=904,
        away_team_name="Research Away",
        home_score=2,
        away_score=1,
        home_hits=None,
        away_hits=None,
        home_errors=None,
        away_errors=None,
        home_innings={},
        away_innings={},
        source_payload_ref="s3://raw/research-old.json",
        source_payload_checksum="c" * 64,
    )
    corrected = GameHistorySnapshot(
        snapshot_id=str(uuid.uuid4()),
        provider=old.provider,
        provider_game_id=old.provider_game_id,
        observed_at="2026-09-27T10:00:00+00:00",
        scheduled_first_pitch=old.scheduled_first_pitch,
        provider_timezone=old.provider_timezone,
        status_long=old.status_long,
        status_short=old.status_short,
        league_id=old.league_id,
        season=old.season,
        home_team_id=old.home_team_id,
        home_team_name=old.home_team_name,
        away_team_id=old.away_team_id,
        away_team_name=old.away_team_name,
        home_score=7,
        away_score=3,
        home_hits=None,
        away_hits=None,
        home_errors=None,
        away_errors=None,
        home_innings={},
        away_innings={},
        source_payload_ref="s3://raw/research-corrected.json",
        source_payload_checksum="d" * 64,
    )

    with psycopg.connect(database_url) as connection:
        repository = PostgreSQLGameHistoryRepository(connection)
        try:
            assert repository.append_snapshot(old) is True
            assert repository.append_snapshot(corrected) is True
            season_rows = repository.latest_snapshots_for_season(
                league_id=1,
                season=2026,
            )
            matching = [
                row
                for row in season_rows
                if row.provider_game_id == old.provider_game_id
            ]
            assert len(matching) == 1
            assert matching[0].snapshot_id == corrected.snapshot_id
            assert matching[0].home_score == 7
        finally:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM api_sports_game_history_snapshots "
                    "WHERE snapshot_id IN (%s, %s)",
                    (old.snapshot_id, corrected.snapshot_id),
                )
            connection.commit()
