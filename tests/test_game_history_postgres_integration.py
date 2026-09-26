import os
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from quantbot.baseball.db import apply_migrations
from quantbot.baseball.game_history import canonical_game_history
from quantbot.baseball.game_history_repository import PostgreSQLGameHistoryRepository
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
