import os
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from quantbot.baseball.db import apply_migrations
from quantbot.baseball.official_mlb import canonical_pregame_snapshot
from quantbot.baseball.official_mlb_repository import PostgreSQLOfficialMLBRepository
from quantbot.baseball.raw_archive import ArchiveReceipt


def _snapshot():
    payload = {
        "gamePk": 823570,
        "metaData": {"timeStamp": "20260920_151258"},
        "gameData": {
            "datetime": {
                "dateTime": "2026-09-20T17:10:00Z",
                "dayNight": "day",
            },
            "status": {
                "abstractGameState": "Preview",
                "detailedState": "Pre-Game",
            },
            "teams": {
                "away": {"id": 143, "name": "Philadelphia Phillies", "record": {}},
                "home": {"id": 121, "name": "New York Mets", "record": {}},
            },
            "probablePitchers": {
                "away": {"id": 650911, "fullName": "Cristopher Sánchez"},
                "home": {"id": 804636, "fullName": "Jonah Tong"},
            },
            "venue": {
                "id": 3289,
                "name": "Citi Field",
                "fieldInfo": {"roofType": "Open", "turfType": "Grass"},
                "location": {
                    "elevation": 10,
                    "azimuthAngle": 13.0,
                    "defaultCoordinates": {
                        "latitude": 40.75753012,
                        "longitude": -73.84559155,
                    },
                },
                "timeZone": {
                    "id": "America/New_York",
                    "offsetAtGameTime": -4,
                },
            },
        },
        "liveData": {
            "boxscore": {
                "teams": {
                    "away": {"battingOrder": list(range(101, 110)), "bullpen": [201]},
                    "home": {"battingOrder": list(range(301, 310)), "bullpen": [401]},
                }
            }
        },
    }
    return canonical_pregame_snapshot(
        payload,
        ArchiveReceipt(
            ref="s3://raw/mlb-feed.json",
            checksum="a" * 64,
            captured_at=datetime(2026, 9, 26, 8, 0, tzinfo=UTC).isoformat(),
        ),
        requested_timecode="20260920_151000",
    )


def test_official_mlb_snapshot_repository_is_idempotent() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    apply_migrations(Path("."), database_url)
    snapshot = _snapshot()

    with psycopg.connect(database_url) as connection:
        repository = PostgreSQLOfficialMLBRepository(connection)
        assert repository.append_snapshot(snapshot) is True
        assert repository.append_snapshot(snapshot) is False

        row = connection.execute(
            "SELECT mlb_game_pk, source_observed_at, requested_timecode, "
            "away_lineup_count, home_lineup_count, lineup_state, venue_id "
            "FROM official_mlb_pregame_snapshots WHERE snapshot_id = %s",
            (snapshot.snapshot_id,),
        ).fetchone()

    assert row is not None
    assert int(row[0]) == 823570
    assert row[1].isoformat().startswith("2026-09-20T15:12:58")
    assert row[2] == "20260920_151000"
    assert tuple(row[3:6]) == (9, 9, "POPULATED")
    assert int(row[6]) == 3289
