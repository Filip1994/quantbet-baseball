from datetime import UTC, datetime

import pytest

from quantbot.baseball.evidence import EvidenceError
from quantbot.baseball.mlb_feature_snapshot import (
    compose_mlb_pregame_feature_snapshot,
)
from quantbot.baseball.mlb_identity import MLBGameIdentityLink
from quantbot.baseball.official_mlb_components import build_pregame_components
from quantbot.baseball.provider_data import TeamStatisticsSnapshot
from quantbot.baseball.raw_archive import ArchiveReceipt


def _link() -> MLBGameIdentityLink:
    return MLBGameIdentityLink(
        link_id="11111111-1111-4111-8111-111111111111",
        mapping_version="mlb-2026-v1",
        game_id="186584",
        api_sports_provider_game_id=186584,
        mlb_game_pk=900001,
        api_home_team_id=2001,
        api_away_team_id=2002,
        mlb_home_team_id=121,
        mlb_away_team_id=143,
        api_sports_first_pitch="2026-09-27T18:00:00+00:00",
        official_mlb_first_pitch="2026-09-27T18:00:00+00:00",
        kickoff_delta_seconds=0,
        linked_at="2026-09-27T15:00:00+00:00",
        api_fixture_observation_id="22222222-2222-4222-8222-222222222222",
        api_source_payload_ref="s3://raw/api-sports/game.json",
        api_source_payload_checksum="a" * 64,
        mlb_schedule_source_payload_ref="s3://raw/mlb/schedule.json",
        mlb_schedule_source_payload_checksum="b" * 64,
    )


def _payload():
    return {
        "gamePk": 900001,
        "metaData": {"timeStamp": "20260927_162900"},
        "gameData": {
            "datetime": {"dateTime": "2026-09-27T18:00:00Z"},
            "status": {
                "abstractGameState": "Preview",
                "detailedState": "Pre-Game",
            },
            "teams": {
                "away": {"id": 143, "name": "Philadelphia Phillies"},
                "home": {"id": 121, "name": "New York Mets"},
            },
            "probablePitchers": {
                "away": {"id": 650911, "fullName": "Away Starter"},
                "home": {"id": 804636, "fullName": "Home Starter"},
            },
            "venue": {
                "id": 3289,
                "name": "Citi Field",
                "fieldInfo": {
                    "roofType": "Open",
                    "turfType": "Grass",
                },
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
                        "bullpen": [201, 202, 203],
                    },
                    "home": {
                        "battingOrder": list(range(301, 310)),
                        "bullpen": [401, 402],
                    },
                }
            }
        },
    }


def _components(*, retrieved_at="2026-09-27T16:30:00+00:00"):
    return build_pregame_components(
        _payload(),
        ArchiveReceipt(
            ref="s3://raw/mlb/live.json",
            checksum="c" * 64,
            captured_at=retrieved_at,
        ),
    )


def _stats(*, team_id: int, side: str, checksum_char: str):
    home = side == "home"
    return TeamStatisticsSnapshot(
        snapshot_id=f"stats-{team_id}",
        provider="api-sports-baseball",
        league_id=1,
        season=2026,
        team_id=team_id,
        team_name="Team",
        observed_at="2026-09-27T16:00:00+00:00",
        games_played_all=150,
        games_played_home=75,
        games_played_away=75,
        wins_all=90,
        wins_home=48 if home else 42,
        wins_away=42 if home else 48,
        win_pct_all=0.6,
        win_pct_home=0.64 if home else 0.56,
        win_pct_away=0.56 if home else 0.64,
        losses_all=60,
        losses_home=27 if home else 33,
        losses_away=33 if home else 27,
        loss_pct_all=0.4,
        loss_pct_home=0.36 if home else 0.44,
        loss_pct_away=0.44 if home else 0.36,
        runs_for_total_all=750.0,
        runs_for_total_home=390.0,
        runs_for_total_away=360.0,
        runs_for_avg_all=5.0,
        runs_for_avg_home=5.2 if home else 4.8,
        runs_for_avg_away=4.8 if home else 5.2,
        runs_against_total_all=600.0,
        runs_against_total_home=285.0,
        runs_against_total_away=315.0,
        runs_against_avg_all=4.0,
        runs_against_avg_home=3.8 if home else 4.2,
        runs_against_avg_away=4.2 if home else 3.8,
        source_payload_ref=f"s3://raw/api-sports/stats-{team_id}.json",
        source_payload_checksum=checksum_char * 64,
    )


def test_composes_model_safe_mlb_pregame_snapshot() -> None:
    snapshot = compose_mlb_pregame_feature_snapshot(
        link=_link(),
        components=_components(),
        home_team_statistics=_stats(team_id=2001, side="home", checksum_char="d"),
        away_team_statistics=_stats(team_id=2002, side="away", checksum_char="e"),
        generated_at=datetime(2026, 9, 27, 16, 31, tzinfo=UTC),
    )

    assert snapshot.game_id == "186584"
    assert snapshot.feature_version == "mlb-pregame-v1"
    assert snapshot.source_data_cutoff_at == "2026-09-27T16:30:00+00:00"
    assert snapshot.features["home_starter_known"] is True
    assert snapshot.features["away_starter_state"] == "PROBABLE"
    assert snapshot.features["home_lineup_state"] == "POPULATED"
    assert snapshot.features["home_lineup_count"] == 9
    assert snapshot.features["away_bullpen_count"] == 3
    assert snapshot.features["venue_roof_type"] == "Open"
    assert snapshot.features["home_team_win_pct"] == pytest.approx(0.64)
    assert snapshot.features["away_team_win_pct"] == pytest.approx(0.64)
    assert snapshot.features["home_team_run_differential_per_game"] == pytest.approx(
        1.4
    )
    assert snapshot.null_reasons == {}
    assert len(snapshot.sources) == 3
    assert not any(name.endswith("_id") for name in snapshot.features)


def test_missing_team_statistics_remain_explicit_nulls() -> None:
    snapshot = compose_mlb_pregame_feature_snapshot(
        link=_link(),
        components=_components(),
        home_team_statistics=None,
        away_team_statistics=None,
        generated_at=datetime(2026, 9, 27, 16, 31, tzinfo=UTC),
    )

    assert snapshot.features["home_team_win_pct"] is None
    assert snapshot.features["away_team_runs_per_game"] is None
    assert (
        snapshot.null_reasons["home_team_win_pct"]
        == "TEAM_STATISTICS_UNAVAILABLE_AT_CUTOFF"
    )
    assert len(snapshot.sources) == 1


def test_rejects_component_not_retrieved_by_generated_at() -> None:
    with pytest.raises(EvidenceError, match="unavailable at generated_at"):
        compose_mlb_pregame_feature_snapshot(
            link=_link(),
            components=_components(retrieved_at="2026-09-27T16:40:00+00:00"),
            home_team_statistics=None,
            away_team_statistics=None,
            generated_at=datetime(2026, 9, 27, 16, 31, tzinfo=UTC),
        )


def test_rejects_component_game_identity_mismatch() -> None:
    rows = list(_components())
    object.__setattr__(rows[0], "mlb_game_pk", 999999)

    with pytest.raises(EvidenceError, match="game identity mismatch"):
        compose_mlb_pregame_feature_snapshot(
            link=_link(),
            components=tuple(rows),
            home_team_statistics=None,
            away_team_statistics=None,
            generated_at=datetime(2026, 9, 27, 16, 31, tzinfo=UTC),
        )
