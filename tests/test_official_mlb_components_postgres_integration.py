import os
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from quantbot.baseball.db import apply_migrations
from quantbot.baseball.official_mlb import canonical_pregame_snapshot
from quantbot.baseball.official_mlb_component_repository import (
    PostgreSQLOfficialMLBComponentRepository,
)
from quantbot.baseball.official_mlb_components import build_pregame_components
from quantbot.baseball.raw_archive import ArchiveReceipt


def _snapshot():
    payload = {
        "gamePk": 823570,
        "metaData": {"timeStamp": "20260920_151258"},
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
                "away": {"id": 650911, "fullName": "Cristopher Sanchez"},
                "home": {"id": 804636, "fullName": "Jonah Tong"},
            },
            "venue": {
                "id": 3289,
                "name": "Citi Field",
                "fieldInfo": {},
                "location": {},
                "timeZone": {},
            },
        },
        "liveData": {
            "boxscore": {
                "teams": {
                    "away": {
                        "battingOrder": list(range(101, 110)),
                        "bullpen": [],
                    },
                    "home": {
                        "battingOrder": list(range(201, 210)),
                        "bullpen": [],
                    },
                }
            }
        },
    }
    return canonical_pregame_snapshot(
        payload,
        ArchiveReceipt(
            ref="s3://raw/component-feed.json",
            checksum="c" * 64,
            captured_at="2026-09-20T15:20:00+00:00",
        ),
        requested_timecode="20260920_151000",
    )


def test_component_repository_is_idempotent_and_enforces_system_known_at() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    apply_migrations(Path("."), database_url)

    starters, lineups = build_pregame_components(_snapshot())

    with psycopg.connect(database_url) as connection:
        repository = PostgreSQLOfficialMLBComponentRepository(connection)
        for record in starters:
            assert repository.append_starter(record) is True
            assert repository.append_starter(record) is False
        for record in lineups:
            assert repository.append_lineup(record) is True
            assert repository.append_lineup(record) is False

        before_retrieval = datetime(2026, 9, 20, 15, 15, tzinfo=UTC)
        assert (
            repository.latest_starter_known_at(
                mlb_game_pk=823570,
                side="AWAY",
                as_of=before_retrieval,
            )
            is None
        )
        assert (
            repository.latest_lineup_known_at(
                mlb_game_pk=823570,
                side="AWAY",
                as_of=before_retrieval,
            )
            is None
        )

        known_cutoff = datetime(2026, 9, 20, 15, 21, tzinfo=UTC)
        starter = repository.latest_starter_known_at(
            mlb_game_pk=823570,
            side="AWAY",
            as_of=known_cutoff,
        )
        lineup = repository.latest_lineup_known_at(
            mlb_game_pk=823570,
            side="AWAY",
            as_of=known_cutoff,
        )

        after_pitch = datetime(2026, 9, 20, 17, 11, tzinfo=UTC)
        assert (
            repository.latest_starter_known_at(
                mlb_game_pk=823570,
                side="AWAY",
                as_of=after_pitch,
            )
            is None
        )
        assert (
            repository.latest_lineup_known_at(
                mlb_game_pk=823570,
                side="AWAY",
                as_of=after_pitch,
            )
            is None
        )

    assert starter is not None
    assert starter.starter_state == "PROBABLE"
    assert starter.pitcher_id == 650911
    assert lineup is not None
    assert lineup.lineup_state == "POPULATED"
    assert lineup.confirmation_state == "NOT_ASSERTED"
    assert lineup.batting_order_ids == tuple(range(101, 110))
