from quantbot.baseball.decision_lifecycle import RegisteredPick
from quantbot.baseball.evidence import OddsObservation
from quantbot.baseball.monitoring_lifecycle import ClosingFinalization
from quantbot.baseball.settlement_lifecycle import (
    GameResultFact,
    build_pick_settlement,
)


def _pick(selection: str = "home") -> RegisteredPick:
    return RegisteredPick(
        pick_id="pick-1",
        verification_id="verification-1",
        final_evaluation_id="evaluation-1",
        prediction_id="prediction-1",
        game_id="20",
        market_family="moneyline",
        selection=selection,
        bookmaker="book-a",
        entry_observation_id="entry-home",
        entry_odds=2.00,
        model_probability=0.55,
        market_probability=0.4871794872,
        fair_decimal_odds=1.818181,
        edge=0.0628205128,
        expected_value_per_unit=0.10,
        uncertainty_metric=0.02,
        model_version="baseline-v1",
        feature_snapshot_ref="feature://20",
        source_data_cutoff_at="2026-09-20T16:59:00+00:00",
        kickoff_at="2026-09-20T19:00:00+00:00",
        registered_at="2026-09-20T17:02:07+00:00",
        paper_mode=True,
        state="REGISTERED",
    )


def _result(*, home_score: int, away_score: int) -> GameResultFact:
    winner = (
        "home"
        if home_score > away_score
        else "away"
        if away_score > home_score
        else "tie"
    )
    return GameResultFact(
        result_id=f"result-{home_score}-{away_score}",
        game_id="20",
        fixture_observation_id="fixture-final",
        provider_status="FT",
        observed_at="2026-09-20T22:00:00+00:00",
        home_score=home_score,
        away_score=away_score,
        winner=winner,
        source_payload_ref="s3://raw/final.json",
        source_payload_checksum="a" * 64,
    )


def _observation(
    observation_id: str,
    *,
    selection: str,
    odds: float,
) -> OddsObservation:
    return OddsObservation(
        observation_id=observation_id,
        game_id="20",
        market_family="moneyline",
        line=None,
        selection=selection,
        bookmaker="book-a",
        decimal_odds=odds,
        raw_price=str(odds),
        observed_at="2026-09-20T18:50:00+00:00",
        retrieved_at="2026-09-20T18:50:00+00:00",
        source_payload_ref=f"s3://raw/{observation_id}.json",
        source_payload_checksum="b" * 64,
        schema_version="1.0",
        market_status="open",
        kickoff_at="2026-09-20T19:00:00+00:00",
    )


def _closing(outcome: str) -> ClosingFinalization:
    captured = outcome == "CAPTURED"
    stale = outcome == "STALE_QUOTE"
    return ClosingFinalization(
        finalization_id="closing-1",
        pick_id="pick-1",
        game_id="20",
        fixture_observation_id="fixture-cutoff",
        cutoff_at="2026-09-20T19:00:00+00:00",
        bookmaker="book-a",
        selection="home",
        finalized_at="2026-09-20T19:00:01+00:00",
        outcome=outcome,
        candidate_home_observation_id="close-home" if captured or stale else None,
        candidate_away_observation_id="close-away" if captured or stale else None,
        closing_observation_id="close-home" if captured else None,
        lifecycle_policy_version="BASEBALL_ODDS_LIFECYCLE_V1",
        closing_max_age_seconds=1200,
    )


def test_captured_close_produces_realized_clv_and_win_profit() -> None:
    home = _observation("close-home", selection="home", odds=1.85)
    away = _observation("close-away", selection="away", odds=2.05)
    settlement = build_pick_settlement(
        _pick(),
        _result(home_score=5, away_score=3),
        _closing("CAPTURED"),
        settled_at="2026-09-20T22:00:01+00:00",
        closing_pair=(home, away),
    )

    assert settlement.outcome == "WIN"
    assert settlement.profit_per_unit == 1.0
    assert settlement.paper_stake_rsd == 300
    assert settlement.paper_profit_rsd == 300.0
    assert settlement.clv_status == "AVAILABLE"
    assert settlement.closing_odds == 1.85
    assert settlement.clv_probability_delta is not None
    assert settlement.clv_probability_delta > 0
    assert settlement.clv_price_ratio is not None
    assert settlement.clv_price_ratio > 0


def test_stale_close_never_fabricates_clv() -> None:
    settlement = build_pick_settlement(
        _pick(),
        _result(home_score=2, away_score=4),
        _closing("STALE_QUOTE"),
        settled_at="2026-09-20T22:00:01+00:00",
        closing_pair=None,
    )

    assert settlement.outcome == "LOSS"
    assert settlement.profit_per_unit == -1.0
    assert settlement.paper_stake_rsd == 300
    assert settlement.paper_profit_rsd == -300.0
    assert settlement.clv_status == "UNAVAILABLE_STALE_QUOTE"
    assert settlement.closing_odds is None
    assert settlement.clv_probability_delta is None


def test_tied_final_result_is_an_explicit_push() -> None:
    settlement = build_pick_settlement(
        _pick(),
        _result(home_score=3, away_score=3),
        _closing("NO_VALID_QUOTE"),
        settled_at="2026-09-20T22:00:01+00:00",
        closing_pair=None,
    )

    assert settlement.outcome == "PUSH"
    assert settlement.profit_per_unit == 0.0
    assert settlement.paper_stake_rsd == 300
    assert settlement.paper_profit_rsd == 0.0
    assert settlement.clv_status == "UNAVAILABLE_NO_VALID_QUOTE"
