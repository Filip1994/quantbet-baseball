import pytest

from quantbot.baseball.moneyline_historical_evaluation import (
    HistoricalMoneylineEvaluation,
    HistoricalMoneylineExample,
)
from quantbot.baseball.moneyline_historical_report import (
    build_historical_report,
    calibration_bins,
)


def _example(game_id: int, probability: float, home_win: int):
    brier = (probability - home_win) ** 2
    return HistoricalMoneylineExample(
        provider_game_id=game_id,
        scheduled_first_pitch=f"2026-06-{game_id:02d}T18:00:00+00:00",
        home_team_id=10,
        away_team_id=20,
        model_version="team-strength-poisson-baseline-v1",
        evaluation_mode="EVENT_TIME_RECONSTRUCTION",
        home_probability=probability,
        away_probability=1.0 - probability,
        home_expected_runs=4.8,
        away_expected_runs=4.2,
        home_overall_games=50,
        home_context_games=25,
        away_overall_games=50,
        away_context_games=25,
        target_home_win=home_win,
        brier_loss=brier,
        log_loss=0.5,
        correct=int((probability >= 0.5) == bool(home_win)),
    )


def _evaluation(examples):
    count = len(examples)
    return HistoricalMoneylineEvaluation(
        model_version="team-strength-poisson-baseline-v1",
        evaluation_mode="EVENT_TIME_RECONSTRUCTION",
        games_available=count,
        examples=count,
        skipped_insufficient_or_invalid=0,
        brier_score=sum(row.brier_loss for row in examples) / count,
        log_loss=sum(row.log_loss for row in examples) / count,
        accuracy=sum(row.correct for row in examples) / count,
        shrinkage_games=30.0,
        min_overall_games=10,
        min_context_games=5,
    )


def test_calibration_bins_compare_prediction_with_observed_rate() -> None:
    examples = (
        _example(1, 0.42, 0),
        _example(2, 0.44, 1),
        _example(3, 0.62, 1),
        _example(4, 0.66, 1),
    )

    bins = calibration_bins(examples, bin_count=10)

    assert bins[4]["count"] == 2
    assert bins[4]["mean_probability"] == pytest.approx(0.43)
    assert bins[4]["observed_home_win_rate"] == pytest.approx(0.5)
    assert bins[6]["count"] == 2
    assert bins[6]["mean_probability"] == pytest.approx(0.64)
    assert bins[6]["observed_home_win_rate"] == pytest.approx(1.0)


def test_build_report_exposes_metrics_distribution_and_time_window(monkeypatch) -> None:
    examples = (
        _example(1, 0.40, 0),
        _example(2, 0.60, 1),
        _example(3, 0.70, 1),
    )
    evaluation = _evaluation(examples)

    def fake_evaluate(repository, **kwargs):
        assert repository is fake_repository
        assert kwargs["league_id"] == 1
        assert kwargs["season"] == 2026
        return evaluation, examples

    fake_repository = object()
    monkeypatch.setattr(
        "quantbot.baseball.moneyline_historical_report."
        "evaluate_historical_moneyline_from_repository",
        fake_evaluate,
    )

    report = build_historical_report(
        fake_repository,
        league_id=1,
        season=2026,
    )

    assert report["evaluation"]["examples"] == 3
    assert report["probability_distribution"]["minimum_home_probability"] == 0.40
    assert report["probability_distribution"]["maximum_home_probability"] == 0.70
    assert report["probability_distribution"]["mean_home_probability"] == pytest.approx(
        0.5666666667
    )
    assert report["probability_distribution"]["observed_home_win_rate"] == pytest.approx(
        2 / 3
    )
    assert report["first_example_first_pitch"] == examples[0].scheduled_first_pitch
    assert report["last_example_first_pitch"] == examples[-1].scheduled_first_pitch


def test_calibration_bins_require_multiple_bins() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        calibration_bins((_example(1, 0.5, 1),), bin_count=1)
