from datetime import UTC, datetime

from quantbot.baseball.fixture_evidence import FixtureObservation
from quantbot.baseball.moneyline_baseline import project_team_strength_moneyline
from quantbot.baseball.moneyline_core_materialization import (
    materialize_due_moneyline_core_v1_features,
)
from quantbot.baseball.moneyline_features import (
    CORE_FEATURE_VERSION,
    build_moneyline_core_v1_feature_snapshot,
)
from quantbot.baseball.provider_data import TeamStatisticsSnapshot


def _fixture() -> FixtureObservation:
    return FixtureObservation(
        fixture_observation_id="11111111-1111-4111-8111-111111111111",
        game_id="900001",
        provider="api-sports-baseball",
        provider_game_id=900001,
        league="NPB",
        home_team_id=10,
        home_team_name="Yomiuri Giants",
        away_team_id=20,
        away_team_name="Yakult Swallows",
        kickoff_at="2030-07-04T19:20:00+00:00",
        provider_status="NS",
        observed_at="2030-07-04T15:50:00+00:00",
        source_payload_ref="s3://raw/npb-games.json",
        source_payload_checksum="f" * 64,
        schema_version="1.0",
    )


def _stats(
    team_id: int, name: str, *, home: bool, checksum: str
) -> TeamStatisticsSnapshot:
    split_win = 0.62 if home else 0.48
    split_rf = 4.9 if home else 4.2
    split_ra = 3.8 if home else 4.5
    return TeamStatisticsSnapshot(
        snapshot_id=f"stats-{team_id}",
        provider="api-sports-baseball",
        league_id=2,
        season=2030,
        team_id=team_id,
        team_name=name,
        observed_at="2030-07-04T15:55:00+00:00",
        games_played_all=80,
        games_played_home=40,
        games_played_away=40,
        wins_all=44,
        wins_home=25 if home else 19,
        wins_away=19 if home else 25,
        win_pct_all=0.55,
        win_pct_home=split_win if home else 0.55,
        win_pct_away=0.55 if home else split_win,
        losses_all=36,
        losses_home=15 if home else 21,
        losses_away=21 if home else 15,
        loss_pct_all=0.45,
        loss_pct_home=(1 - split_win) if home else 0.45,
        loss_pct_away=0.45 if home else (1 - split_win),
        runs_for_total_all=360.0,
        runs_for_total_home=split_rf * 40 if home else 180.0,
        runs_for_total_away=180.0 if home else split_rf * 40,
        runs_for_avg_all=4.5,
        runs_for_avg_home=split_rf if home else 4.5,
        runs_for_avg_away=4.5 if home else split_rf,
        runs_against_total_all=336.0,
        runs_against_total_home=split_ra * 40 if home else 168.0,
        runs_against_total_away=168.0 if home else split_ra * 40,
        runs_against_avg_all=4.2,
        runs_against_avg_home=split_ra if home else 4.2,
        runs_against_avg_away=4.2 if home else split_ra,
        source_payload_ref=f"s3://raw/npb-team-{team_id}.json",
        source_payload_checksum=checksum * 64,
    )


def test_npb_core_snapshot_requires_no_mlb_identity_or_components() -> None:
    snapshot = build_moneyline_core_v1_feature_snapshot(
        fixture=_fixture(),
        home_team_statistics=_stats(10, "Yomiuri Giants", home=True, checksum="a"),
        away_team_statistics=_stats(20, "Yakult Swallows", home=False, checksum="b"),
        generated_at=datetime(2030, 7, 4, 16, 0, tzinfo=UTC),
    )

    assert snapshot.feature_version == CORE_FEATURE_VERSION
    assert snapshot.features["home_context_runs_per_game"] == 4.9
    assert snapshot.features["away_context_runs_per_game"] == 4.2
    assert "home_starter_state" not in snapshot.features
    assert len(snapshot.sources) == 2

    projection = project_team_strength_moneyline(snapshot)
    assert projection.home_probability + projection.away_probability == 1.0
    assert projection.context_status == "CORE_TEAM_STRENGTH_ONLY"


class _FixtureRepo:
    def __init__(self):
        self.fixture = _fixture()

    def latest_due_core_fixtures(self, *, as_of, horizon_minutes, league_names):
        assert "NPB" in league_names
        return (self.fixture,)

    def latest_fixture_observation(self, *, game_id, as_of):
        return self.fixture if game_id == self.fixture.game_id else None


class _ProviderRepo:
    def latest_team_statistics(self, *, league_id, season, team_id, as_of):
        assert league_id == 2
        if team_id == 10:
            return _stats(10, "Yomiuri Giants", home=True, checksum="a")
        if team_id == 20:
            return _stats(20, "Yakult Swallows", home=False, checksum="b")
        return None


class _FeatureRepo:
    def __init__(self):
        self.snapshot = None

    def latest_for_game_version(self, *, game_id, feature_version, as_of):
        if (
            self.snapshot is not None
            and self.snapshot.game_id == game_id
            and self.snapshot.feature_version == feature_version
        ):
            return self.snapshot
        return None

    def append(self, snapshot):
        if self.snapshot is not None:
            return False
        self.snapshot = snapshot
        return True


def test_core_materialization_is_restart_safe() -> None:
    fixtures = _FixtureRepo()
    provider = _ProviderRepo()
    features = _FeatureRepo()
    now = datetime(2030, 7, 4, 18, 0, tzinfo=UTC)

    first = materialize_due_moneyline_core_v1_features(
        fixtures,
        provider,
        features,
        league_ids=(2,),
        now=now,
        horizon_minutes=120,
    )
    second = materialize_due_moneyline_core_v1_features(
        fixtures,
        provider,
        features,
        league_ids=(2,),
        now=now,
        horizon_minutes=120,
    )

    assert first["status"] == "COMPLETE"
    assert first["snapshots_inserted"] == 1
    assert first["provider_calls"] == 0
    assert second["status"] == "COMPLETE"
    assert second["already_materialized"] == 1
    assert second["snapshots_inserted"] == 0
