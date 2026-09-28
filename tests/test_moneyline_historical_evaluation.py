from dataclasses import replace

import pytest

from quantbot.baseball.game_history import GameHistorySnapshot
from quantbot.baseball.moneyline_historical_evaluation import (
    EVALUATION_MODE,
    evaluate_historical_moneyline_baseline,
    reconstruct_historical_example,
    reconstruct_team_rates,
)


def _game(
    game_id: int,
    first_pitch: str,
    *,
    home_id: int,
    away_id: int,
    home_score: int,
    away_score: int,
    observed_at: str | None = None,
) -> GameHistorySnapshot:
    return GameHistorySnapshot(
        snapshot_id=f"snapshot-{game_id}-{observed_at or first_pitch}",
        provider="api-sports-baseball",
        provider_game_id=game_id,
        observed_at=observed_at or first_pitch,
        scheduled_first_pitch=first_pitch,
        provider_timezone="UTC",
        status_long="Finished",
        status_short="FT",
        league_id=1,
        season=2030,
        home_team_id=home_id,
        home_team_name=f"Team {home_id}",
        away_team_id=away_id,
        away_team_name=f"Team {away_id}",
        home_score=home_score,
        away_score=away_score,
        home_hits=None,
        away_hits=None,
        home_errors=None,
        away_errors=None,
        home_innings={},
        away_innings={},
        source_payload_ref=f"s3://raw/game-{game_id}.json",
        source_payload_checksum="a" * 64,
    )


def _history():
    return (
        _game(
            1,
            "2030-04-01T18:00:00+00:00",
            home_id=10,
            away_id=30,
            home_score=6,
            away_score=3,
        ),
        _game(
            2,
            "2030-04-02T18:00:00+00:00",
            home_id=31,
            away_id=10,
            home_score=2,
            away_score=5,
        ),
        _game(
            3,
            "2030-04-01T19:00:00+00:00",
            home_id=40,
            away_id=20,
            home_score=3,
            away_score=4,
        ),
        _game(
            4,
            "2030-04-02T19:00:00+00:00",
            home_id=20,
            away_id=41,
            home_score=6,
            away_score=2,
        ),
    )


def _target(*, home_score: int = 5, away_score: int = 3):
    return _game(
        100,
        "2030-04-10T18:00:00+00:00",
        home_id=10,
        away_id=20,
        home_score=home_score,
        away_score=away_score,
    )


def test_reconstructs_prior_only_overall_and_context_rates() -> None:
    home = reconstruct_team_rates(
        target=_target(),
        team_id=10,
        context_site="HOME",
        history=_history(),
        min_overall_games=2,
        min_context_games=1,
    )
    away = reconstruct_team_rates(
        target=_target(),
        team_id=20,
        context_site="AWAY",
        history=_history(),
        min_overall_games=2,
        min_context_games=1,
    )

    assert home is not None
    assert home.overall_games == 2
    assert home.context_games == 1
    assert home.runs_for == 11
    assert home.runs_against == 5
    assert home.context_runs_for == 6
    assert home.context_runs_against == 3
    assert home.overall_win_pct == 1.0

    assert away is not None
    assert away.overall_games == 2
    assert away.context_games == 1
    assert away.runs_for == 10
    assert away.runs_against == 5
    assert away.context_runs_for == 4
    assert away.context_runs_against == 3


def test_target_result_changes_label_but_not_projection() -> None:
    history = _history()
    home_win = reconstruct_historical_example(
        _target(home_score=5, away_score=3),
        history,
        min_overall_games=2,
        min_context_games=1,
    )
    away_win = reconstruct_historical_example(
        _target(home_score=2, away_score=7),
        history,
        min_overall_games=2,
        min_context_games=1,
    )

    assert home_win is not None
    assert away_win is not None
    assert home_win.home_probability == pytest.approx(away_win.home_probability)
    assert home_win.away_probability == pytest.approx(away_win.away_probability)
    assert home_win.home_expected_runs == pytest.approx(away_win.home_expected_runs)
    assert home_win.away_expected_runs == pytest.approx(away_win.away_expected_runs)
    assert home_win.target_home_win == 1
    assert away_win.target_home_win == 0


def test_future_game_cannot_change_earlier_projection() -> None:
    target = _target()
    base = reconstruct_historical_example(
        target,
        _history(),
        min_overall_games=2,
        min_context_games=1,
    )
    future = _game(
        200,
        "2030-04-11T18:00:00+00:00",
        home_id=10,
        away_id=20,
        home_score=25,
        away_score=0,
        observed_at="2030-05-01T00:00:00+00:00",
    )
    with_future = reconstruct_historical_example(
        target,
        (*_history(), future),
        min_overall_games=2,
        min_context_games=1,
    )

    assert base is not None
    assert with_future is not None
    assert base.home_probability == pytest.approx(with_future.home_probability)
    assert base.away_probability == pytest.approx(with_future.away_probability)
    assert base.home_expected_runs == pytest.approx(with_future.home_expected_runs)
    assert base.away_expected_runs == pytest.approx(with_future.away_expected_runs)


def test_reconstruction_uses_latest_snapshot_for_prior_event() -> None:
    old = _game(
        1,
        "2030-04-01T18:00:00+00:00",
        home_id=10,
        away_id=30,
        home_score=2,
        away_score=1,
        observed_at="2030-04-01T22:00:00+00:00",
    )
    corrected = replace(
        old,
        snapshot_id="snapshot-1-corrected",
        observed_at="2030-05-01T00:00:00+00:00",
        home_score=6,
        away_score=3,
        source_payload_checksum="b" * 64,
    )
    history = (old, corrected, *_history()[1:])

    home = reconstruct_team_rates(
        target=_target(),
        team_id=10,
        context_site="HOME",
        history=history,
        min_overall_games=2,
        min_context_games=1,
    )

    assert home is not None
    assert home.context_runs_for == 6
    assert home.context_runs_against == 3


def test_insufficient_history_fails_closed() -> None:
    example = reconstruct_historical_example(
        _target(),
        _history()[:1],
        min_overall_games=2,
        min_context_games=1,
    )

    assert example is None


def test_evaluation_is_chronological_and_explicitly_research_reconstruction() -> None:
    rows = (*_history(), _target())
    evaluation, examples = evaluate_historical_moneyline_baseline(
        rows,
        min_overall_games=2,
        min_context_games=1,
    )

    assert evaluation.evaluation_mode == EVALUATION_MODE
    assert evaluation.games_available == 5
    assert evaluation.examples == 1
    assert evaluation.skipped_insufficient_or_invalid == 4
    assert evaluation.brier_score is not None
    assert evaluation.log_loss is not None
    assert evaluation.accuracy in {0.0, 1.0}
    assert len(examples) == 1
    assert examples[0].provider_game_id == 100
    assert examples[0].evaluation_mode == EVALUATION_MODE


def test_later_retrieval_time_does_not_masquerade_as_system_known_replay() -> None:
    later_retrieved_prior = replace(
        _history()[0],
        snapshot_id="late-retrieval",
        observed_at="2030-06-01T00:00:00+00:00",
    )
    example = reconstruct_historical_example(
        _target(),
        (later_retrieved_prior, *_history()[1:]),
        min_overall_games=2,
        min_context_games=1,
    )

    assert example is not None
    assert example.evaluation_mode == "EVENT_TIME_RECONSTRUCTION"
