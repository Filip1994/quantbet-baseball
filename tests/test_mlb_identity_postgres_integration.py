import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from quantbot.baseball.db import apply_migrations
from quantbot.baseball.fixture_evidence import (
    FixtureObservation,
    build_fixture_schedule_snapshot,
)
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
        group_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        target_receipt = ArchiveReceipt(
            ref=_fixture().source_payload_ref,
            checksum=_fixture().source_payload_checksum,
            captured_at=_fixture().observed_at,
        )
        next_receipt = ArchiveReceipt(
            ref="s3://raw/api-sports/games-next.json",
            checksum="e" * 64,
            captured_at="2026-09-20T13:00:01+00:00",
        )
        assert evidence.append_fixture_schedule_snapshot(
            build_fixture_schedule_snapshot(
                snapshot_group_id=group_id,
                query_date="2026-09-20",
                records=(_fixture(),),
                response_rows=1,
                receipt=target_receipt,
            )
        )
        assert evidence.append_fixture_schedule_snapshot(
            build_fixture_schedule_snapshot(
                snapshot_group_id=group_id,
                query_date="2026-09-21",
                records=(),
                response_rows=0,
                receipt=next_receipt,
            )
        )

        repository = PostgreSQLMLBIdentityRepository(connection)
        fixtures = repository.latest_mlb_fixtures_for_schedule_date(
            date_iso="2026-09-20",
            observed_by=datetime(2026, 9, 20, 17, 0, tzinfo=UTC),
        )
        fixture_by_id = {item.provider_game_id: item for item in fixtures}
        assert 186584 in fixture_by_id
        assert fixture_by_id[186584] == _fixture()

        provider_date_fixtures = repository.latest_mlb_fixtures_for_provider_query_date(
            date_iso="2026-09-20",
            observed_by=datetime(2026, 9, 20, 17, 0, tzinfo=UTC),
        )
        assert provider_date_fixtures == (_fixture(),)

        assert repository.append_team_mappings_atomically(mappings) == 2
        assert repository.append_team_mappings_atomically(mappings) == 0
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


def test_identity_repository_excludes_fixture_removed_from_latest_complete_schedule() -> (
    None
):
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    apply_migrations(Path("."), database_url)

    early_ref = "s3://raw/api-sports/games-early.json"
    late_ref = "s3://raw/api-sports/games-late.json"
    stale = replace(
        _fixture(),
        fixture_observation_id="33333333-3333-4333-8333-333333333333",
        game_id="187571",
        provider_game_id=187571,
        home_team_id=5,
        home_team_name="Boston Red Sox",
        away_team_id=6,
        away_team_name="Chicago Cubs",
        kickoff_at="2026-09-20T23:15:00+00:00",
        observed_at="2026-09-20T08:15:00+00:00",
        source_payload_ref=early_ref,
        source_payload_checksum="1" * 64,
    )
    active_early = replace(
        _fixture(),
        fixture_observation_id="44444444-4444-4444-8444-444444444444",
        game_id="187566",
        provider_game_id=187566,
        home_team_id=20,
        home_team_name="Milwaukee Brewers",
        away_team_id=33,
        away_team_name="St.Louis Cardinals",
        kickoff_at="2026-09-20T23:10:00+00:00",
        observed_at="2026-09-20T08:15:00+00:00",
        source_payload_ref=early_ref,
        source_payload_checksum="1" * 64,
    )
    active_late = replace(
        active_early,
        fixture_observation_id="55555555-5555-4555-8555-555555555555",
        observed_at="2026-09-20T22:31:00+00:00",
        source_payload_ref=late_ref,
        source_payload_checksum="2" * 64,
    )

    with psycopg.connect(database_url) as connection:
        evidence = PostgreSQLEvidenceRepository(connection)
        assert evidence.append_fixture_observations((stale, active_early)) == 2
        early_group = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        assert evidence.append_fixture_schedule_snapshot(
            build_fixture_schedule_snapshot(
                snapshot_group_id=early_group,
                query_date="2026-09-20",
                records=(stale, active_early),
                response_rows=2,
                receipt=ArchiveReceipt(
                    ref=early_ref,
                    checksum="1" * 64,
                    captured_at="2026-09-20T08:15:00+00:00",
                ),
            )
        )
        assert evidence.append_fixture_schedule_snapshot(
            build_fixture_schedule_snapshot(
                snapshot_group_id=early_group,
                query_date="2026-09-21",
                records=(),
                response_rows=0,
                receipt=ArchiveReceipt(
                    ref="s3://raw/api-sports/games-next-early.json",
                    checksum="3" * 64,
                    captured_at="2026-09-20T08:15:01+00:00",
                ),
            )
        )

        assert evidence.append_fixture_observations((active_late,)) == 1
        late_group = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        assert evidence.append_fixture_schedule_snapshot(
            build_fixture_schedule_snapshot(
                snapshot_group_id=late_group,
                query_date="2026-09-20",
                records=(active_late,),
                response_rows=1,
                receipt=ArchiveReceipt(
                    ref=late_ref,
                    checksum="2" * 64,
                    captured_at="2026-09-20T22:31:00+00:00",
                ),
            )
        )
        assert evidence.append_fixture_schedule_snapshot(
            build_fixture_schedule_snapshot(
                snapshot_group_id=late_group,
                query_date="2026-09-21",
                records=(),
                response_rows=0,
                receipt=ArchiveReceipt(
                    ref="s3://raw/api-sports/games-next-late.json",
                    checksum="4" * 64,
                    captured_at="2026-09-20T22:31:01+00:00",
                ),
            )
        )

        repository = PostgreSQLMLBIdentityRepository(connection)
        fixtures = repository.latest_mlb_fixtures_for_schedule_date(
            date_iso="2026-09-20",
            observed_by=datetime(2026, 9, 20, 22, 40, tzinfo=UTC),
        )

    assert [fixture.provider_game_id for fixture in fixtures] == [187566]
    assert fixtures[0].source_payload_ref == late_ref
