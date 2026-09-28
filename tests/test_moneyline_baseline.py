import math

import pytest

from quantbot.baseball.evidence import EvidenceError
from quantbot.baseball.feature_snapshot import FeatureSource, build_feature_snapshot
from quantbot.baseball.moneyline_baseline import (
    MODEL_VERSION,
    canonical_team_strength_projection_json,
    project_team_strength_moneyline,
)


def _snapshot(*, full_context: bool = True, feature_version: str = "moneyline-v1"):
    features = {
        "home_overall_sample_games": 80,
        "home_overall_win_pct": 0.60,
        "home_overall_runs_per_game": 5.0,
        "home_overall_runs_allowed_per_game": 4.2,
        "home_overall_run_differential_per_game": 0.8,
        "home_context_sample_games": 40,
        "home_context_win_pct": 0.65,
        "home_context_runs_per_game": 5.4,
        "home_context_runs_allowed_per_game": 4.0,
        "home_context_run_differential_per_game": 1.4,
        "away_overall_sample_games": 80,
        "away_overall_win_pct": 0.54,
        "away_overall_runs_per_game": 4.8,
        "away_overall_runs_allowed_per_game": 4.5,
        "away_overall_run_differential_per_game": 0.3,
        "away_context_sample_games": 40,
        "away_context_win_pct": 0.49,
        "away_context_runs_per_game": 4.5,
        "away_context_runs_allowed_per_game": 4.8,
        "away_context_run_differential_per_game": -0.3,
        "home_starter_state": "PROBABLE" if full_context else "ABSENT",
        "home_starter_identified": full_context,
        "away_starter_state": "PROBABLE" if full_context else "ABSENT",
        "away_starter_identified": full_context,
        "home_lineup_state": "POPULATED" if full_context else "PARTIAL",
        "home_lineup_slots": 9 if full_context else 6,
        "home_lineup_populated": full_context,
        "away_lineup_state": "POPULATED" if full_context else "PARTIAL",
        "away_lineup_slots": 9 if full_context else 7,
        "away_lineup_populated": full_context,
        "home_bullpen_state": "PRESENT" if full_context else "ABSENT",
        "home_bullpen_members": 8 if full_context else 0,
        "away_bullpen_state": "PRESENT" if full_context else "ABSENT",
        "away_bullpen_members": 8 if full_context else 0,
        "venue_id": "777",
        "venue_roof_type": "Open",
        "venue_turf_type": "Grass",
        "venue_elevation_ft": 35,
    }
    return build_feature_snapshot(
        game_id="990100",
        feature_version=feature_version,
        generated_at="2030-07-04T16:05:00+00:00",
        kickoff_at="2030-07-04T19:20:00+00:00",
        features=features,
        sources=(
            FeatureSource(
                source_name="test-source",
                observed_at="2030-07-04T16:00:00+00:00",
                retrieved_at="2030-07-04T16:00:00+00:00",
                source_payload_ref="s3://raw/features.json",
                source_payload_checksum="a" * 64,
                field_names=tuple(sorted(features)),
            ),
        ),
    )


def test_team_strength_baseline_shrinks_splits_and_returns_two_way_probability() -> (
    None
):
    projection = project_team_strength_moneyline(_snapshot(), shrinkage_games=30.0)

    home_weight = 40 / 70
    expected_home_offense = home_weight * 5.4 + (1 - home_weight) * 5.0
    expected_home_defense = home_weight * 4.0 + (1 - home_weight) * 4.2
    expected_away_offense = home_weight * 4.5 + (1 - home_weight) * 4.8
    expected_away_defense = home_weight * 4.8 + (1 - home_weight) * 4.5

    assert projection.model_version == MODEL_VERSION
    assert projection.home_offense_rate == pytest.approx(expected_home_offense)
    assert projection.home_defense_rate == pytest.approx(expected_home_defense)
    assert projection.away_offense_rate == pytest.approx(expected_away_offense)
    assert projection.away_defense_rate == pytest.approx(expected_away_defense)
    assert projection.home_expected_runs == pytest.approx(
        math.sqrt(expected_home_offense * expected_away_defense)
    )
    assert projection.away_expected_runs == pytest.approx(
        math.sqrt(expected_away_offense * expected_home_defense)
    )
    assert projection.home_probability + projection.away_probability == pytest.approx(
        1.0
    )
    assert projection.home_probability > projection.away_probability
    assert projection.minimum_context_games == 40
    assert projection.context_status == "FULL_PREGAME_CONTEXT"


def test_unvalidated_pregame_identity_state_does_not_change_probability() -> None:
    full = project_team_strength_moneyline(_snapshot(full_context=True))
    limited = project_team_strength_moneyline(_snapshot(full_context=False))

    assert full.home_probability == pytest.approx(limited.home_probability)
    assert full.away_probability == pytest.approx(limited.away_probability)
    assert full.home_expected_runs == pytest.approx(limited.home_expected_runs)
    assert full.context_status == "FULL_PREGAME_CONTEXT"
    assert limited.context_status == "LIMITED_CONTEXT"


def test_projection_is_deterministic_and_canonical() -> None:
    first = project_team_strength_moneyline(_snapshot(), shrinkage_games=25.0)
    second = project_team_strength_moneyline(_snapshot(), shrinkage_games=25.0)

    assert first == second
    assert first.projection_id == second.projection_id
    assert '"model_version":"team-strength-poisson-baseline-v1"' in (
        canonical_team_strength_projection_json(first)
    )


def test_baseline_rejects_wrong_feature_contract() -> None:
    with pytest.raises(EvidenceError, match="feature_version=moneyline-v1"):
        project_team_strength_moneyline(_snapshot(feature_version="other-v1"))


def test_baseline_rejects_nonpositive_run_rate() -> None:
    snapshot = _snapshot()
    broken_features = dict(snapshot.features)
    broken_features["home_context_runs_per_game"] = 0.0
    broken = build_feature_snapshot(
        game_id=snapshot.game_id,
        feature_version=snapshot.feature_version,
        generated_at=snapshot.generated_at,
        kickoff_at=snapshot.kickoff_at,
        features=broken_features,
        sources=snapshot.sources,
        null_reasons=snapshot.null_reasons,
    )

    with pytest.raises(
        EvidenceError, match="home_context_runs_per_game must be positive"
    ):
        project_team_strength_moneyline(broken)


@pytest.mark.parametrize("value", [0.0, -1.0, float("inf"), float("nan")])
def test_baseline_rejects_invalid_shrinkage(value) -> None:
    with pytest.raises(ValueError, match="shrinkage_games"):
        project_team_strength_moneyline(_snapshot(), shrinkage_games=value)
