import os
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from quantbot.baseball.db import apply_migrations
from quantbot.baseball.feature_snapshot_repository import (
    PostgreSQLFeatureSnapshotRepository,
)
from quantbot.baseball.fixture_evidence import canonical_fixture_observation
from quantbot.baseball.mlb_identity import MLBGameIdentityLink
from quantbot.baseball.mlb_identity_repository import PostgreSQLMLBIdentityRepository
from quantbot.baseball.moneyline_features import (
    assemble_and_persist_moneyline_v1_feature_snapshot,
)
from quantbot.baseball.official_mlb_component_repository import (
    PostgreSQLOfficialMLBComponentRepository,
)
from quantbot.baseball.official_mlb_components import build_pregame_components
from quantbot.baseball.postgres_repository import PostgreSQLEvidenceRepository
from quantbot.baseball.provider_data import canonical_team_statistics
from quantbot.baseball.provider_data_repository import PostgreSQLProviderDataRepository
from quantbot.baseball.raw_archive import ArchiveReceipt

_PROVIDER_GAME_ID = 990200
_GAME_ID = str(_PROVIDER_GAME_ID)
_GAME_PK = 880200
_KICKOFF = "2030-07-05T19:20:00+00:00"


def _receipt(ref: str, checksum_char: str, captured_at: str) -> ArchiveReceipt:
    return ArchiveReceipt(
        ref=ref,
        checksum=checksum_char * 64,
        captured_at=captured_at,
    )


def _fixture():
    row = canonical_fixture_observation(
        {
            "id": _PROVIDER_GAME_ID,
            "date": _KICKOFF,
            "league": {"name": "MLB"},
            "status": {"short": "NS"},
            "teams": {
                "home": {"id": 31, "name": "Home Integration"},
                "away": {"id": 41, "name": "Away Integration"},
            },
        },
        _receipt(
            "s3://raw/integration-schedule.json",
            "d",
            "2030-07-05T15:00:00+00:00",
        ),
    )
    assert row is not None
    return row


def _team_payload(*, team_id: int, name: str, home_team: bool):
    if home_team:
        home_pct, away_pct = 0.64, 0.52
        home_rf, away_rf = 5.3, 4.6
        home_ra, away_ra = 4.0, 4.4
    else:
        home_pct, away_pct = 0.55, 0.48
        home_rf, away_rf = 4.9, 4.5
        home_ra, away_ra = 4.4, 4.8
    return {
        "team": {"id": team_id, "name": name},
        "league": {"id": 1, "season": 2030},
        "games": {
            "played": {"all": 80, "home": 40, "away": 40},
            "wins": {
                "all": {"total": 46, "percentage": 0.575},
                "home": {"total": round(40 * home_pct), "percentage": home_pct},
                "away": {"total": round(40 * away_pct), "percentage": away_pct},
            },
            "loses": {
                "all": {"total": 34, "percentage": 0.425},
                "home": {
                    "total": 40 - round(40 * home_pct),
                    "percentage": 1.0 - home_pct,
                },
                "away": {
                    "total": 40 - round(40 * away_pct),
                    "percentage": 1.0 - away_pct,
                },
            },
        },
        "points": {
            "for": {
                "total": {
                    "all": 396.0,
                    "home": home_rf * 40,
                    "away": away_rf * 40,
                },
                "average": {
                    "all": 4.95,
                    "home": home_rf,
                    "away": away_rf,
                },
            },
            "against": {
                "total": {
                    "all": 352.0,
                    "home": home_ra * 40,
                    "away": away_ra * 40,
                },
                "average": {
                    "all": 4.4,
                    "home": home_ra,
                    "away": away_ra,
                },
            },
        },
    }


def _components():
    payload = {
        "gamePk": _GAME_PK,
        "metaData": {"timeStamp": "20300705_155000"},
        "gameData": {
            "datetime": {"dateTime": _KICKOFF},
            "status": {
                "abstractGameState": "Preview",
                "detailedState": "Pre-Game",
            },
            "teams": {
                "home": {"id": 131, "name": "Home Integration"},
                "away": {"id": 141, "name": "Away Integration"},
            },
            "probablePitchers": {
                "home": {"id": 7001, "fullName": "Home Starter"},
                "away": {"id": 7002, "fullName": "Away Starter"},
            },
            "venue": {
                "id": 9001,
                "name": "Integration Park",
                "fieldInfo": {"roofType": "Open", "turfType": "Grass"},
                "location": {
                    "elevation": 50,
                    "defaultCoordinates": {
                        "latitude": 40.0,
                        "longitude": -74.0,
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
                    "home": {
                        "battingOrder": list(range(301, 310)),
                        "bullpen": [401, 402, 403],
                    },
                    "away": {
                        "battingOrder": list(range(101, 110)),
                        "bullpen": [201, 202],
                    },
                }
            }
        },
    }
    return build_pregame_components(
        payload,
        _receipt(
            "s3://raw/integration-mlb-feed.json",
            "c",
            "2030-07-05T16:00:00+00:00",
        ),
    )


def _identity_link(fixture) -> MLBGameIdentityLink:
    return MLBGameIdentityLink(
        link_id="11111111-2222-4333-8444-555555555555",
        mapping_version="mlb-2030-v1",
        game_id=_GAME_ID,
        api_sports_provider_game_id=_PROVIDER_GAME_ID,
        mlb_game_pk=_GAME_PK,
        api_home_team_id=31,
        api_away_team_id=41,
        mlb_home_team_id=131,
        mlb_away_team_id=141,
        api_sports_first_pitch=_KICKOFF,
        official_mlb_first_pitch=_KICKOFF,
        kickoff_delta_seconds=0,
        linked_at="2030-07-05T15:10:00+00:00",
        api_fixture_observation_id=fixture.fixture_observation_id,
        api_source_payload_ref=fixture.source_payload_ref,
        api_source_payload_checksum=fixture.source_payload_checksum,
        mlb_schedule_source_payload_ref="s3://raw/integration-mlb-schedule.json",
        mlb_schedule_source_payload_checksum="e" * 64,
    )


def test_moneyline_v1_assembles_from_postgres_point_in_time_evidence() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    apply_migrations(Path("."), database_url)

    fixture = _fixture()
    home_stats = canonical_team_statistics(
        _team_payload(team_id=31, name="Home Integration", home_team=True),
        _receipt(
            "s3://raw/integration-home-stats.json",
            "a",
            "2030-07-05T15:55:00+00:00",
        ),
    )
    away_stats = canonical_team_statistics(
        _team_payload(team_id=41, name="Away Integration", home_team=False),
        _receipt(
            "s3://raw/integration-away-stats.json",
            "b",
            "2030-07-05T15:54:00+00:00",
        ),
    )

    with psycopg.connect(database_url) as connection:
        fixture_repository = PostgreSQLEvidenceRepository(connection)
        identity_repository = PostgreSQLMLBIdentityRepository(connection)
        provider_repository = PostgreSQLProviderDataRepository(connection)
        component_repository = PostgreSQLOfficialMLBComponentRepository(connection)
        feature_repository = PostgreSQLFeatureSnapshotRepository(connection)

        fixture_repository.append_fixture_observations((fixture,))
        provider_repository.append_team_statistics(home_stats)
        provider_repository.append_team_statistics(away_stats)
        identity_repository.append_game_link(_identity_link(fixture))
        component_repository.append_components(_components())

        as_of = datetime(2030, 7, 5, 16, 5, tzinfo=UTC)
        snapshot, inserted = assemble_and_persist_moneyline_v1_feature_snapshot(
            fixture_repository,
            identity_repository,
            provider_repository,
            component_repository,
            feature_repository,
            provider_game_id=_PROVIDER_GAME_ID,
            mapping_version="mlb-2030-v1",
            as_of=as_of,
        )
        replay, replay_inserted = assemble_and_persist_moneyline_v1_feature_snapshot(
            fixture_repository,
            identity_repository,
            provider_repository,
            component_repository,
            feature_repository,
            provider_game_id=_PROVIDER_GAME_ID,
            mapping_version="mlb-2030-v1",
            as_of=as_of,
        )
        stored = feature_repository.get(snapshot.snapshot_id)

    assert inserted is True
    assert replay_inserted is False
    assert replay == snapshot
    assert stored == snapshot
    assert snapshot.features["home_context_win_pct"] == 0.64
    assert snapshot.features["away_context_win_pct"] == 0.48
    assert snapshot.features["venue_id"] == "9001"
    assert snapshot.source_data_cutoff_at == "2030-07-05T16:00:00+00:00"
