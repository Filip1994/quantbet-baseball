from datetime import UTC, datetime

import pytest

from quantbot.baseball.feature_snapshot import FeatureSource, build_feature_snapshot
from quantbot.baseball.moneyline_features import CORE_FEATURE_VERSION
from quantbot.baseball.moneyline_prediction_materialization import (
    materialize_due_baseline_predictions,
    uncertainty_proxy,
)


def _snapshot(game_id: str = "123"):
    features = {
        "home_overall_runs_per_game": 5.0,
        "home_context_runs_per_game": 5.2,
        "home_overall_runs_allowed_per_game": 4.1,
        "home_context_runs_allowed_per_game": 4.0,
        "home_context_sample_games": 40,
        "away_overall_runs_per_game": 4.4,
        "away_context_runs_per_game": 4.2,
        "away_overall_runs_allowed_per_game": 4.8,
        "away_context_runs_allowed_per_game": 4.9,
        "away_context_sample_games": 32,
    }
    return build_feature_snapshot(
        game_id=game_id,
        feature_version=CORE_FEATURE_VERSION,
        generated_at="2030-07-04T15:00:00+00:00",
        kickoff_at="2030-07-04T19:00:00+00:00",
        features=features,
        sources=(
            FeatureSource(
                source_name="test",
                observed_at="2030-07-04T14:55:00+00:00",
                retrieved_at="2030-07-04T14:55:00+00:00",
                source_payload_ref="s3://raw/test.json",
                source_payload_checksum="a" * 64,
                field_names=tuple(sorted(features)),
            ),
        ),
    )


class _FeatureRepo:
    def __init__(self, snapshots):
        self.snapshots = tuple(snapshots)

    def due_for_prediction(
        self,
        *,
        feature_versions,
        as_of,
        horizon_minutes,
        limit,
    ):
        assert CORE_FEATURE_VERSION in feature_versions
        assert horizon_minutes == 360
        return self.snapshots[:limit]


class _DecisionRepo:
    def __init__(self):
        self.by_feature = {}

    def get_prediction_for_feature_snapshot(
        self,
        *,
        model_version,
        feature_snapshot_ref,
    ):
        return self.by_feature.get((model_version, feature_snapshot_ref))

    def append_prediction(self, record):
        key = (record.model_version, record.feature_snapshot_ref)
        if key in self.by_feature:
            return False
        self.by_feature[key] = record
        return True


def test_uncertainty_proxy_is_inverse_context_sample_size() -> None:
    assert uncertainty_proxy(40) == pytest.approx(0.025)
    assert uncertainty_proxy(20) == pytest.approx(0.05)
    with pytest.raises(ValueError):
        uncertainty_proxy(0)


def test_prediction_canary_is_bounded_and_restart_safe() -> None:
    features = _FeatureRepo((_snapshot("123"), _snapshot("456")))
    decisions = _DecisionRepo()
    now = datetime(2030, 7, 4, 15, 5, tzinfo=UTC)

    first = materialize_due_baseline_predictions(
        features,
        decisions,
        now=now,
        horizon_minutes=360,
        max_predictions=1,
    )
    second = materialize_due_baseline_predictions(
        features,
        decisions,
        now=now,
        horizon_minutes=360,
        max_predictions=1,
    )

    assert first["status"] == "CAPACITY_LIMITED"
    assert first["predictions_considered"] == 1
    assert first["predictions_inserted"] == 1
    assert first["provider_calls"] == 0
    prediction = next(iter(decisions.by_feature.values()))
    assert prediction.game_id == "123"
    assert prediction.uncertainty_metric == pytest.approx(1 / 32)

    assert second["already_predicted"] == 1
    assert second["predictions_considered"] == 1
    assert second["predictions_inserted"] == 1
    assert len(decisions.by_feature) == 2
