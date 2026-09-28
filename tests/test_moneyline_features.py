from datetime import UTC, datetime

import pytest

from quantbot.baseball.evidence import EvidenceError
from quantbot.baseball.fixture_evidence import FixtureObservation
from quantbot.baseball.mlb_identity import MLBGameIdentityLink
from quantbot.baseball.moneyline_features import (
    FEATURE_VERSION,
    assemble_and_persist_moneyline_v1_feature_snapshot,
    build_moneyline_v1_feature_snapshot,
)
from quantbot.baseball.official_mlb_components import build_pregame_components
from quantbot.baseball.provider_data import TeamStatisticsSnapshot
from quantbot.baseball.raw_archive import ArchiveReceipt

_GAME_ID = "990100"
_GAME_PK = 880100
_KICKOFF = "2030-07-04T19:20:00+00:00"


def _fixture() -> FixtureObservation:
    return FixtureObservation(
        fixture_observation_id="fixture-990100",
        game_id=_GAME_ID,
        provider="api-sports-baseball",
        provider_game_id=990100,
        league="MLB",
        home_team_id=10,
        home_team_name="Home Club",
        away_team_id=20,
        away_team_name="Away Club",
        kickoff_at=_KICKOFF,
        provider_status="NS",
        observed_at="2030-07-04T15:00:00+00:00",
        source_payload_ref="s3://raw/schedule.json",
        source_payload_checksum="f" * 64,
        schema_version="1.0",
    )


def _identity_link() -> MLBGameIdentityLink:
    return MLBGameIdentityLink(
        link_id="link-990100",
        mapping_version="mlb-2030-v1",
        game_id=_GAME_ID,
        api_sports_provider_game_id=990100,
        mlb_game_pk=_GAME_PK,
        api_home_team_id=10,
        api_away_team_id=20,
        mlb_home_team_id=110,
        mlb_away_team_id=120,
        api_sports_first_pitch=_KICKOFF,
        official_mlb_first_pitch=_KICKOFF,
        kickoff_delta_seconds=0,
        linked_at="2030-07-04T15:10:00+00:00",
        api_fixture_observation_id="fixture-990100",
        api_source_payload_ref="s3://raw/schedule.json",
        api_source_payload_checksum="f" * 64,
        mlb_schedule_source_payload_ref="s3://raw/mlb-schedule.json",
        mlb_schedule_source_payload_checksum="e" * 64,
    )


def _team_stats(
    *,
    team_id: int,
    name: str,
    observed_at: str,
    checksum_char: str,
    overall_win_pct: float,
    split_win_pct: float,
    overall_runs_for: float,
    split_runs_for: float,
    overall_runs_against: float,
    split_runs_against: float,
    home_team: bool,
) -> TeamStatisticsSnapshot:
    if home_team:
        home_games, away_games = 40, 36
        home_win, away_win = split_win_pct, 0.50
        home_rf, away_rf = split_runs_for, 4.3
        home_ra, away_ra = split_runs_against, 4.2
    else:
        home_games, away_games = 39, 37
        home_win, away_win = 0.51, split_win_pct
        home_rf, away_rf = 4.4, split_runs_for
        home_ra, away_ra = 4.3, split_runs_against

    games_all = home_games + away_games
    return TeamStatisticsSnapshot(
        snapshot_id=f"stats-{team_id}-{checksum_char}",
        provider="api-sports-baseball",
        league_id=1,
        season=2030,
        team_id=team_id,
        team_name=name,
        observed_at=observed_at,
        games_played_all=games_all,
        games_played_home=home_games,
        games_played_away=away_games,
        wins_all=round(games_all * overall_win_pct),
        wins_home=round(home_games * home_win),
        wins_away=round(away_games * away_win),
        win_pct_all=overall_win_pct,
        win_pct_home=home_win,
        win_pct_away=away_win,
        losses_all=games_all - round(games_all * overall_win_pct),
        losses_home=home_games - round(home_games * home_win),
        losses_away=away_games - round(away_games * away_win),
        loss_pct_all=1.0 - overall_win_pct,
        loss_pct_home=1.0 - home_win,
        loss_pct_away=1.0 - away_win,
        runs_for_total_all=overall_runs_for * games_all,
        runs_for_total_home=home_rf * home_games,
        runs_for_total_away=away_rf * away_games,
        runs_for_avg_all=overall_runs_for,
        runs_for_avg_home=home_rf,
        runs_for_avg_away=away_rf,
        runs_against_total_all=overall_runs_against * games_all,
        runs_against_total_home=home_ra * home_games,
        runs_against_total_away=away_ra * away_games,
        runs_against_avg_all=overall_runs_against,
        runs_against_avg_home=home_ra,
        runs_against_avg_away=away_ra,
        source_payload_ref=f"s3://raw/team-{team_id}.json",
        source_payload_checksum=checksum_char * 64,
    )


def _home_stats() -> TeamStatisticsSnapshot:
    return _team_stats(
        team_id=10,
        name="Home Club",
        observed_at="2030-07-04T15:55:00+00:00",
        checksum_char="a",
        overall_win_pct=0.60,
        split_win_pct=0.65,
        overall_runs_for=5.1,
        split_runs_for=5.4,
        overall_runs_against=4.2,
        split_runs_against=4.0,
        home_team=True,
    )


def _away_stats() -> TeamStatisticsSnapshot:
    return _team_stats(
        team_id=20,
        name="Away Club",
        observed_at="2030-07-04T15:54:00+00:00",
        checksum_char="b",
        overall_win_pct=0.54,
        split_win_pct=0.49,
        overall_runs_for=4.8,
        split_runs_for=4.5,
        overall_runs_against=4.5,
        split_runs_against=4.8,
        home_team=False,
    )


def _component_payload(*, roof_type="Open"):
    return {
        "gamePk": _GAME_PK,
        "metaData": {"timeStamp": "20300704_155000"},
        "gameData": {
            "datetime": {"dateTime": _KICKOFF},
            "status": {
                "abstractGameState": "Preview",
                "detailedState": "Pre-Game",
            },
            "teams": {
                "home": {"id": 110, "name": "Home Club"},
                "away": {"id": 120, "name": "Away Club"},
            },
            "probablePitchers": {
                "home": {"id": 501, "fullName": "Home Starter"},
                "away": {"id": 601, "fullName": "Away Starter"},
            },
            "venue": {
                "id": 777,
                "name": "Model Park",
                "fieldInfo": {
                    "roofType": roof_type,
                    "turfType": "Grass",
                },
                "location": {
                    "elevation": 35,
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


def _components(*, roof_type="Open"):
    return build_pregame_components(
        _component_payload(roof_type=roof_type),
        ArchiveReceipt(
            ref="s3://raw/mlb-pregame.json",
            checksum="c" * 64,
            captured_at="2030-07-04T16:00:00+00:00",
        ),
    )


def test_builds_compact_moneyline_v1_snapshot_without_identifier_strength() -> None:
    snapshot = build_moneyline_v1_feature_snapshot(
        fixture=_fixture(),
        identity_link=_identity_link(),
        home_team_statistics=_home_stats(),
        away_team_statistics=_away_stats(),
        components=_components(),
        generated_at=datetime(2030, 7, 4, 16, 5, tzinfo=UTC),
    )

    assert snapshot.feature_version == FEATURE_VERSION
    assert snapshot.source_data_cutoff_at == "2030-07-04T16:00:00+00:00"
    assert snapshot.features["home_overall_win_pct"] == 0.60
    assert snapshot.features["home_context_win_pct"] == 0.65
    assert snapshot.features["away_overall_win_pct"] == 0.54
    assert snapshot.features["away_context_win_pct"] == 0.49
    assert snapshot.features["home_context_run_differential_per_game"] == pytest.approx(
        1.4
    )
    assert snapshot.features["away_context_run_differential_per_game"] == pytest.approx(
        -0.3
    )
    assert snapshot.features["home_starter_identified"] is True
    assert snapshot.features["away_starter_identified"] is True
    assert snapshot.features["home_lineup_slots"] == 9
    assert snapshot.features["away_lineup_slots"] == 9
    assert snapshot.features["home_bullpen_members"] == 3
    assert snapshot.features["away_bullpen_members"] == 2
    assert snapshot.features["venue_id"] == "777"
    assert snapshot.features["venue_roof_type"] == "Open"
    assert snapshot.features["venue_elevation_ft"] == 35
    assert "home_starter_id" not in snapshot.features
    assert "away_starter_id" not in snapshot.features
    assert "home_team_id" not in snapshot.features
    assert "away_team_id" not in snapshot.features
    assert len(snapshot.sources) == 3


def test_optional_venue_field_uses_explicit_null_reason() -> None:
    snapshot = build_moneyline_v1_feature_snapshot(
        fixture=_fixture(),
        identity_link=_identity_link(),
        home_team_statistics=_home_stats(),
        away_team_statistics=_away_stats(),
        components=_components(roof_type=None),
        generated_at=datetime(2030, 7, 4, 16, 5, tzinfo=UTC),
    )

    assert snapshot.features["venue_roof_type"] is None
    assert (
        snapshot.null_reasons["venue_roof_type"]
        == "OFFICIAL_MLB_ROOF_TYPE_MISSING"
    )


def test_missing_mlb_component_fails_closed() -> None:
    with pytest.raises(EvidenceError, match="incomplete Official MLB component set"):
        build_moneyline_v1_feature_snapshot(
            fixture=_fixture(),
            identity_link=_identity_link(),
            home_team_statistics=_home_stats(),
            away_team_statistics=_away_stats(),
            components=_components()[:-1],
            generated_at=datetime(2030, 7, 4, 16, 5, tzinfo=UTC),
        )


def test_component_retrieved_after_cutoff_fails_closed() -> None:
    components = _components()
    with pytest.raises(EvidenceError, match="not known by cutoff"):
        build_moneyline_v1_feature_snapshot(
            fixture=_fixture(),
            identity_link=_identity_link(),
            home_team_statistics=_home_stats(),
            away_team_statistics=_away_stats(),
            components=components,
            generated_at=datetime(2030, 7, 4, 15, 59, tzinfo=UTC),
        )


class _FixtureRepository:
    def latest_fixture_observation(self, *, game_id, as_of):
        assert game_id == _GAME_ID
        assert as_of == datetime(2030, 7, 4, 16, 5, tzinfo=UTC)
        return _fixture()


class _IdentityRepository:
    def game_link_for_provider_game(self, *, mapping_version, provider_game_id):
        assert mapping_version == "mlb-2030-v1"
        assert provider_game_id == 990100
        return _identity_link()


class _ProviderRepository:
    def latest_team_statistics(self, *, league_id, season, team_id, as_of):
        assert league_id == 1
        assert season == 2030
        assert as_of == datetime(2030, 7, 4, 16, 5, tzinfo=UTC)
        if team_id == 10:
            return _home_stats()
        if team_id == 20:
            return _away_stats()
        return None


class _ComponentRepository:
    def latest_components_for_game(self, *, mlb_game_pk, as_of):
        assert mlb_game_pk == _GAME_PK
        assert as_of == datetime(2030, 7, 4, 16, 5, tzinfo=UTC)
        return _components()


class _FeatureRepository:
    def __init__(self):
        self.rows = []

    def append(self, snapshot):
        self.rows.append(snapshot)
        return True


def test_repository_orchestrator_resolves_and_persists_snapshot() -> None:
    feature_repository = _FeatureRepository()
    snapshot, inserted = assemble_and_persist_moneyline_v1_feature_snapshot(
        _FixtureRepository(),
        _IdentityRepository(),
        _ProviderRepository(),
        _ComponentRepository(),
        feature_repository,
        provider_game_id=990100,
        mapping_version="mlb-2030-v1",
        as_of=datetime(2030, 7, 4, 16, 5, tzinfo=UTC),
    )

    assert inserted is True
    assert feature_repository.rows == [snapshot]
    assert snapshot.game_id == _GAME_ID
    assert snapshot.feature_version == FEATURE_VERSION
