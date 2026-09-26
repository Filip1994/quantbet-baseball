import os
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from quantbot.baseball.db import apply_migrations
from quantbot.baseball.fixture_evidence import FixtureObservation
from quantbot.baseball.mlb_identity import (
    MLBTeamIdentityRegistry,
    link_fixture_to_mlb_game,
    propose_team_identity_mappings,
)
from quantbot.baseball.mlb_identity_repository import PostgreSQLMLBIdentityRepository
from quantbot.baseball.postgres_repository import PostgreSQLEvidenceRepository
from quantbot.baseball.raw_archive import ArchiveReceipt


def _fixture():
    return FixtureObservation(
        fixture_observation_id="22222222-2222-4222-8222-222222222222",
        game_id="186584",
        provider="api-sports-baseball",
        provider_game_id=186584,
        league="MLB",
        home_team_id=2001,
        home_team_name="New York Mets",
        away_team_id=2002,
        away_team_name="Philadelphia Phillies",
        kickoff_at="2026-09-20T17:10:00+00:00",
        provider_status="NS",
        observed_at="2026-09-20T13:00:00+00:00",
        source_payload_ref="s3://raw/api-sports/games.json",
        source_payload_checksum="c" * 64,
        schema_version="1.0",
    )


def _receipt():
    return ArchiveReceipt(
        ref="s3://raw/official-mlb/schedule.json",
        checksum="d" * 64,
        captured_at="2026-09-20T13:05:00+00:00",
    )


def _schedule():
    return {
        "dates": [
            {
                "games": [
                    {
                        "gamePk": 823570,
                        "gameDate": "2026-09-20T17:12:00Z",
                        "teams": {
                            "home": {"team": {"id": 121, "name": "New York Mets"}},
                            "away": {
                                "team": {
                                    "id": 143,
                                    "name": "Philadelphia Phillies",
                                }
                            },
                        },
                    }
                ]
            }
        ]
    }


def test_mlb_identity_repository_is_immutable_and_idempotent() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    apply_migrations(Path("."), database_url)

    mappings = propose_team_identity_mappings(
        _fixture(),
        _schedule(),
        _receipt(),
        mapping_version="integration-2026-v1",
        verified_at=datetime(2026, 9, 20, 13, 5, tzinfo=UTC),
    )
    registry = MLBTeamIdentityRegistry(mappings)
    link = link_fixture_to_mlb_game(
        _fixture(),
        _schedule(),
        _receipt(),
        registry,
    )

    with psycopg.connect(database_url) as connection:
        evidence = PostgreSQLEvidenceRepository(connection)
        assert evidence.append_fixture_observations((_fixture(),)) == 1

        repository = PostgreSQLMLBIdentityRepository(connection)
        fixtures = repository.latest_mlb_fixtures_around_date(
            date_iso="2026-09-20",
            observed_by=datetime(2026, 9, 20, 17, 0, tzinfo=UTC),
            padding=__import__("datetime").timedelta(hours=12),
        )
        assert [item.provider_game_id for item in fixtures] == [186584]

        assert repository.append_team_mapping(mappings[0]) is True
        assert repository.append_team_mapping(mappings[1]) is True
        assert repository.append_team_mapping(mappings[0]) is False
        assert repository.append_game_link(link) is True
        assert repository.append_game_link(link) is False
        stored_link = repository.game_link_for_provider_game(
            mapping_version="integration-2026-v1",
            provider_game_id=186584,
        )
        assert stored_link == link

        stored = repository.team_mappings("integration-2026-v1")
        row = connection.execute(
            "SELECT api_sports_provider_game_id, mlb_game_pk, "
            "kickoff_delta_seconds, mapping_version "
            "FROM official_mlb_game_identity_links WHERE link_id = %s",
            (link.link_id,),
        ).fetchone()

    assert len(stored) == 2
    assert {item.official_mlb_team_id for item in stored} == {121, 143}
    assert row is not None
    assert tuple(row) == (186584, 823570, 120, "integration-2026-v1")
