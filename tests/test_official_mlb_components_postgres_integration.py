import os
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from quantbot.baseball.db import apply_migrations
from quantbot.baseball.official_mlb_component_repository import (
    PostgreSQLOfficialMLBComponentRepository,
)
from quantbot.baseball.official_mlb_components import build_pregame_components
from quantbot.baseball.raw_archive import ArchiveReceipt


def _payload(*, timestamp: str, home_pitcher_id: int):
    return {
        "gamePk": 823570,
        "metaData": {"timeStamp": timestamp},
        "gameData": {
            "datetime": {"dateTime": "2026-09-20T17:10:00Z"},
            "status": {
                "abstractGameState": "Preview",
                "detailedState": "Pre-Game",
            },
            "teams": {
                "away": {"id": 143, "name": "Philadelphia Phillies"},
                "home": {"id": 121, "name": "New York Mets"},
            },
            "probablePitchers": {
                "away": {"id": 650911, "fullName": "Cristopher Sánchez"},
                "home": {"id": home_pitcher_id, "fullName": "Home Starter"},
            },
            "venue": {
                "id": 3289,
                "name": "Citi Field",
                "fieldInfo": {"roofType": "Open", "turfType": "Grass"},
                "location": {
                    "elevation": 10,
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
                    "away": {
                        "battingOrder": list(range(101, 110)),
                        "bullpen": [201, 202],
                    },
                    "home": {
                        "battingOrder": list(range(301, 310)),
                        "bullpen": [401, 402],
                    },
                }
            }
        },
    }


def _rows(*, timestamp: str, checksum: str, home_pitcher_id: int):
    payload = _payload(timestamp=timestamp, home_pitcher_id=home_pitcher_id)
    observed = datetime.strptime(timestamp, "%Y%m%d_%H%M%S").replace(tzinfo=UTC)
    return build_pregame_components(
        payload,
        ArchiveReceipt(
            ref=f"s3://raw/mlb-feed-{checksum[:4]}.json",
            checksum=checksum,
            captured_at=observed.isoformat(),
        ),
    )


def test_component_repository_is_atomic_idempotent_and_point_in_time() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    apply_migrations(Path("."), database_url)

    early = _rows(
        timestamp="20260920_151258",
        checksum="a" * 64,
        home_pitcher_id=804636,
    )
    late = _rows(
        timestamp="20260920_152258",
        checksum="b" * 64,
        home_pitcher_id=999001,
    )

    with psycopg.connect(database_url) as connection:
        repository = PostgreSQLOfficialMLBComponentRepository(connection)
        assert repository.append_components(early) == 7
        assert repository.append_components(early) == 0
        assert repository.append_components(late) == 7

        before_late = repository.latest_component(
            mlb_game_pk=823570,
            component_type="STARTER",
            side="HOME",
            as_of=datetime(2026, 9, 20, 15, 20, tzinfo=UTC),
        )
        after_late = repository.latest_component(
            mlb_game_pk=823570,
            component_type="STARTER",
            side="HOME",
            as_of=datetime(2026, 9, 20, 15, 30, tzinfo=UTC),
        )
        latest = repository.latest_components_for_game(
            mlb_game_pk=823570,
            as_of=datetime(2026, 9, 20, 15, 30, tzinfo=UTC),
        )

    assert before_late is not None
    assert before_late.data["pitcher_id"] == 804636
    assert after_late is not None
    assert after_late.data["pitcher_id"] == 999001
    assert len(latest) == 7
    assert {(item.component_type, item.side) for item in latest} == {
        ("STARTER", "AWAY"),
        ("STARTER", "HOME"),
        ("LINEUP", "AWAY"),
        ("LINEUP", "HOME"),
        ("BULLPEN", "AWAY"),
        ("BULLPEN", "HOME"),
        ("VENUE", "GAME"),
    }


def test_component_repository_rejects_naive_as_of() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    apply_migrations(Path("."), database_url)

    with psycopg.connect(database_url) as connection:
        repository = PostgreSQLOfficialMLBComponentRepository(connection)
        with pytest.raises(ValueError, match="timezone-aware"):
            repository.latest_components_for_game(
                mlb_game_pk=823570,
                as_of=datetime(2026, 9, 20, 15, 30),  # noqa: DTZ001 - intentional
            )
