from dataclasses import replace

import pytest

from quantbot.baseball.decision_lifecycle import (
    build_model_prediction,
    build_moneyline_pair_evaluations,
    build_registered_pick,
    ready_verification,
    requested_verification,
    select_best_candidate,
)
from quantbot.baseball.evidence import EvidenceError, OddsObservation


def _observation(
    *,
    observation_id: str,
    selection: str,
    odds: float,
    observed_at: str,
    bookmaker: str = "bet365",
) -> OddsObservation:
    return OddsObservation(
        observation_id=observation_id,
        game_id="123",
        market_family="moneyline",
        line=None,
        selection=selection,
        bookmaker=bookmaker,
        decimal_odds=odds,
        raw_price=str(odds),
        observed_at=observed_at,
        retrieved_at=observed_at,
        source_payload_ref=f"s3://raw/{observation_id}.json",
        source_payload_checksum="a" * 64,
        schema_version="1.0",
        market_status="open",
        kickoff_at="2026-09-20T19:00:00+00:00",
    )


def _prediction():
    return build_model_prediction(
        game_id="123",
        model_version="baseline-v1",
        feature_snapshot_ref="feature://123/1700",
        source_data_cutoff_at="2026-09-20T16:59:00+00:00",
        predicted_at="2026-09-20T17:00:00+00:00",
        home_probability=0.55,
        away_probability=0.45,
        uncertainty_metric=0.02,
    )


def test_prediction_identity_is_deterministic() -> None:
    assert _prediction() == _prediction()


def test_preliminary_pair_selects_only_value_side() -> None:
    home = _observation(
        observation_id="00000000-0000-0000-0000-000000000001",
        selection="home",
        odds=2.10,
        observed_at="2026-09-20T17:00:00+00:00",
    )
    away = _observation(
        observation_id="00000000-0000-0000-0000-000000000002",
        selection="away",
        odds=1.80,
        observed_at="2026-09-20T17:00:00+00:00",
    )

    evaluations = build_moneyline_pair_evaluations(
        _prediction(),
        home,
        away,
        stage="PRELIMINARY",
        evaluated_at="2026-09-20T17:01:00+00:00",
        min_edge=0.02,
        min_expected_value=0.0,
        max_uncertainty=0.05,
        max_quote_age_seconds=300,
    )

    candidate = select_best_candidate(evaluations)
    assert candidate is not None
    assert candidate.selection == "home"
    assert candidate.outcome == "CANDIDATE"
    assert candidate.expected_value_per_unit > 0.0
    assert evaluations[1].outcome == "PASS"


def test_stale_quote_fails_closed() -> None:
    home = _observation(
        observation_id="00000000-0000-0000-0000-000000000003",
        selection="home",
        odds=2.10,
        observed_at="2026-09-20T17:00:00+00:00",
    )
    away = _observation(
        observation_id="00000000-0000-0000-0000-000000000004",
        selection="away",
        odds=1.80,
        observed_at="2026-09-20T17:00:00+00:00",
    )

    evaluations = build_moneyline_pair_evaluations(
        _prediction(),
        home,
        away,
        stage="PRELIMINARY",
        evaluated_at="2026-09-20T17:10:00+00:00",
        min_edge=0.02,
        min_expected_value=0.0,
        max_uncertainty=0.05,
        max_quote_age_seconds=300,
    )

    assert all(item.outcome == "PASS" for item in evaluations)
    assert {item.reason_code for item in evaluations} == {"STALE_QUOTE"}


def test_ready_final_quote_can_register_immutable_paper_pick() -> None:
    preliminary_home = _observation(
        observation_id="00000000-0000-0000-0000-000000000005",
        selection="home",
        odds=2.10,
        observed_at="2026-09-20T17:00:00+00:00",
    )
    preliminary_away = _observation(
        observation_id="00000000-0000-0000-0000-000000000006",
        selection="away",
        odds=1.80,
        observed_at="2026-09-20T17:00:00+00:00",
    )
    prediction = _prediction()
    preliminary = select_best_candidate(
        build_moneyline_pair_evaluations(
            prediction,
            preliminary_home,
            preliminary_away,
            stage="PRELIMINARY",
            evaluated_at="2026-09-20T17:01:00+00:00",
            min_edge=0.02,
            min_expected_value=0.0,
            max_uncertainty=0.05,
            max_quote_age_seconds=300,
        )
    )
    assert preliminary is not None

    request = requested_verification(
        preliminary,
        requested_at="2026-09-20T17:01:30+00:00",
    )

    final_home = _observation(
        observation_id="00000000-0000-0000-0000-000000000007",
        selection="home",
        odds=2.00,
        observed_at="2026-09-20T17:02:00+00:00",
    )
    final_away = _observation(
        observation_id="00000000-0000-0000-0000-000000000008",
        selection="away",
        odds=1.90,
        observed_at="2026-09-20T17:02:00+00:00",
    )
    final_evaluations = build_moneyline_pair_evaluations(
        prediction,
        final_home,
        final_away,
        stage="FINAL",
        evaluated_at="2026-09-20T17:02:10+00:00",
        min_edge=0.02,
        min_expected_value=0.0,
        max_uncertainty=0.05,
        max_quote_age_seconds=120,
    )
    final_home_evaluation = next(
        item for item in final_evaluations if item.selection == request.selection
    )
    assert final_home_evaluation.outcome == "CANDIDATE"

    ready = ready_verification(
        request,
        home=final_home,
        away=final_away,
        final_evaluation=final_home_evaluation,
        decided_at="2026-09-20T17:02:11+00:00",
    )
    pick = build_registered_pick(
        verification=ready,
        final_evaluation=final_home_evaluation,
        prediction=prediction,
        entry_observation=final_home,
        registered_at="2026-09-20T17:02:12+00:00",
    )

    assert ready.status == "READY"
    assert pick.selection == "home"
    assert pick.entry_observation_id == final_home.observation_id
    assert pick.entry_odds == 2.00
    assert pick.paper_mode is True
    assert pick.paper_stake_minor == 30_000
    assert pick.currency == "RSD"
    assert pick.state == "REGISTERED"


def test_non_playable_bookmaker_is_never_selected_as_candidate() -> None:
    home = _observation(
        observation_id="00000000-0000-0000-0000-000000000101",
        selection="home",
        odds=2.30,
        observed_at="2026-09-20T17:00:00+00:00",
        bookmaker="Pinnacle",
    )
    away = _observation(
        observation_id="00000000-0000-0000-0000-000000000102",
        selection="away",
        odds=1.65,
        observed_at="2026-09-20T17:00:00+00:00",
        bookmaker="Pinnacle",
    )

    evaluations = build_moneyline_pair_evaluations(
        _prediction(),
        home,
        away,
        stage="PRELIMINARY",
        evaluated_at="2026-09-20T17:01:00+00:00",
        min_edge=0.0,
        min_expected_value=-1.0,
        max_uncertainty=0.05,
        max_quote_age_seconds=300,
    )

    assert any(item.outcome == "CANDIDATE" for item in evaluations)
    assert select_best_candidate(evaluations) is None


def test_registered_pick_rejects_non_playable_bookmaker() -> None:
    prediction = _prediction()
    preliminary_home = _observation(
        observation_id="00000000-0000-0000-0000-000000000111",
        selection="home",
        odds=2.20,
        observed_at="2026-09-20T17:00:00+00:00",
        bookmaker="WilliamHill",
    )
    preliminary_away = _observation(
        observation_id="00000000-0000-0000-0000-000000000112",
        selection="away",
        odds=1.70,
        observed_at="2026-09-20T17:00:00+00:00",
        bookmaker="WilliamHill",
    )
    preliminary = next(
        item
        for item in build_moneyline_pair_evaluations(
            prediction,
            preliminary_home,
            preliminary_away,
            stage="PRELIMINARY",
            evaluated_at="2026-09-20T17:01:00+00:00",
            min_edge=0.0,
            min_expected_value=-1.0,
            max_uncertainty=0.05,
            max_quote_age_seconds=300,
        )
        if item.selection == "home"
    )
    request = requested_verification(
        preliminary,
        requested_at="2026-09-20T17:01:30+00:00",
    )
    final_home = _observation(
        observation_id="00000000-0000-0000-0000-000000000113",
        selection="home",
        odds=2.15,
        observed_at="2026-09-20T17:02:00+00:00",
        bookmaker="WilliamHill",
    )
    final_away = _observation(
        observation_id="00000000-0000-0000-0000-000000000114",
        selection="away",
        odds=1.72,
        observed_at="2026-09-20T17:02:00+00:00",
        bookmaker="WilliamHill",
    )
    final = next(
        item
        for item in build_moneyline_pair_evaluations(
            prediction,
            final_home,
            final_away,
            stage="FINAL",
            evaluated_at="2026-09-20T17:02:10+00:00",
            min_edge=0.0,
            min_expected_value=-1.0,
            max_uncertainty=0.05,
            max_quote_age_seconds=120,
        )
        if item.selection == "home"
    )
    ready = ready_verification(
        request,
        home=final_home,
        away=final_away,
        final_evaluation=final,
        decided_at="2026-09-20T17:02:11+00:00",
    )

    with pytest.raises(
        EvidenceError,
        match="registered pick bookmaker must be Bet365 or 1xBet",
    ):
        build_registered_pick(
            verification=ready,
            final_evaluation=final,
            prediction=prediction,
            entry_observation=final_home,
            registered_at="2026-09-20T17:02:12+00:00",
        )


def test_registered_pick_rejects_noncanonical_paper_stake() -> None:
    prediction = _prediction()
    home = _observation(
        observation_id="00000000-0000-0000-0000-000000000121",
        selection="home",
        odds=2.10,
        observed_at="2026-09-20T17:00:00+00:00",
        bookmaker="Bet365",
    )
    away = _observation(
        observation_id="00000000-0000-0000-0000-000000000122",
        selection="away",
        odds=1.80,
        observed_at="2026-09-20T17:00:00+00:00",
        bookmaker="Bet365",
    )
    preliminary = select_best_candidate(
        build_moneyline_pair_evaluations(
            prediction,
            home,
            away,
            stage="PRELIMINARY",
            evaluated_at="2026-09-20T17:01:00+00:00",
            min_edge=0.0,
            min_expected_value=-1.0,
            max_uncertainty=0.05,
            max_quote_age_seconds=300,
        )
    )
    assert preliminary is not None
    request = requested_verification(
        preliminary,
        requested_at="2026-09-20T17:01:30+00:00",
    )
    final = next(
        item
        for item in build_moneyline_pair_evaluations(
            prediction,
            home,
            away,
            stage="FINAL",
            evaluated_at="2026-09-20T17:01:40+00:00",
            min_edge=0.0,
            min_expected_value=-1.0,
            max_uncertainty=0.05,
            max_quote_age_seconds=300,
        )
        if item.selection == request.selection
    )
    ready = ready_verification(
        request,
        home=home,
        away=away,
        final_evaluation=final,
        decided_at="2026-09-20T17:01:41+00:00",
    )
    pick = build_registered_pick(
        verification=ready,
        final_evaluation=final,
        prediction=prediction,
        entry_observation=home if ready.selection == "home" else away,
        registered_at="2026-09-20T17:01:42+00:00",
    )

    with pytest.raises(EvidenceError, match="paper stake must be fixed at 300 RSD"):
        replace(pick, paper_stake_minor=50_000)

    with pytest.raises(EvidenceError, match="paper pick currency must be RSD"):
        replace(pick, currency="EUR")
