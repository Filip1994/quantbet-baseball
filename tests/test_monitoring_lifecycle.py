from quantbot.baseball.decision_lifecycle import RegisteredPick
from quantbot.baseball.evidence import OddsObservation
from quantbot.baseball.fixture_evidence import FixtureObservation
from quantbot.baseball.monitoring_lifecycle import (
    OddsLifecyclePolicy,
    build_closing_finalization,
)


def _pick() -> RegisteredPick:
    return RegisteredPick(
        pick_id="00000000-0000-0000-0000-000000000100",
        verification_id="00000000-0000-0000-0000-000000000101",
        final_evaluation_id="00000000-0000-0000-0000-000000000102",
        prediction_id="00000000-0000-0000-0000-000000000103",
        game_id="10",
        market_family="moneyline",
        selection="home",
        bookmaker="Bet365",
        entry_observation_id="00000000-0000-0000-0000-000000000104",
        entry_odds=2.0,
        model_probability=0.55,
        market_probability=0.50,
        fair_decimal_odds=1 / 0.55,
        edge=0.05,
        expected_value_per_unit=0.10,
        uncertainty_metric=0.02,
        model_version="baseline-v1",
        feature_snapshot_ref="feature://10",
        source_data_cutoff_at="2026-09-20T17:00:00+00:00",
        kickoff_at="2026-09-20T19:00:00+00:00",
        registered_at="2026-09-20T17:02:00+00:00",
        paper_mode=True,
        state="REGISTERED",
    )


def _fixture() -> FixtureObservation:
    return FixtureObservation(
        fixture_observation_id="00000000-0000-0000-0000-000000000110",
        game_id="10",
        provider="api-sports-baseball",
        provider_game_id=10,
        league="MLB",
        home_team_id=1001,
        home_team_name="Home",
        away_team_id=1002,
        away_team_name="Away",
        kickoff_at="2026-09-20T19:00:00+00:00",
        provider_status="NS",
        observed_at="2026-09-20T18:55:00+00:00",
        source_payload_ref="s3://raw/game-10.json",
        source_payload_checksum="a" * 64,
        schema_version="1.0",
    )


def _quote(observation_id: str, selection: str, odds: float, observed_at: str):
    return OddsObservation(
        observation_id=observation_id,
        game_id="10",
        market_family="moneyline",
        line=None,
        selection=selection,
        bookmaker="Bet365",
        decimal_odds=odds,
        raw_price=str(odds),
        observed_at=observed_at,
        retrieved_at=observed_at,
        source_payload_ref=f"s3://raw/{observation_id}.json",
        source_payload_checksum="b" * 64,
        schema_version="1.0",
        market_status="open",
        kickoff_at="2026-09-20T19:00:00+00:00",
    )


def test_fresh_pair_captures_selected_closing_observation() -> None:
    home = _quote(
        "00000000-0000-0000-0000-000000000111",
        "home",
        1.95,
        "2026-09-20T18:50:00+00:00",
    )
    away = _quote(
        "00000000-0000-0000-0000-000000000112",
        "away",
        1.95,
        "2026-09-20T18:50:00+00:00",
    )

    closing = build_closing_finalization(
        _pick(),
        _fixture(),
        finalized_at="2026-09-20T19:00:01+00:00",
        policy=OddsLifecyclePolicy(closing_max_age_seconds=1200),
        pair=(home, away),
    )

    assert closing.outcome == "CAPTURED"
    assert closing.closing_observation_id == home.observation_id
    assert closing.candidate_home_observation_id == home.observation_id
    assert closing.candidate_away_observation_id == away.observation_id


def test_stale_pair_is_preserved_but_not_claimed_as_close() -> None:
    home = _quote(
        "00000000-0000-0000-0000-000000000113",
        "home",
        1.95,
        "2026-09-20T18:30:00+00:00",
    )
    away = _quote(
        "00000000-0000-0000-0000-000000000114",
        "away",
        1.95,
        "2026-09-20T18:30:00+00:00",
    )

    closing = build_closing_finalization(
        _pick(),
        _fixture(),
        finalized_at="2026-09-20T19:00:01+00:00",
        policy=OddsLifecyclePolicy(closing_max_age_seconds=1200),
        pair=(home, away),
    )

    assert closing.outcome == "STALE_QUOTE"
    assert closing.closing_observation_id is None
    assert closing.candidate_home_observation_id == home.observation_id


def test_missing_pair_records_no_valid_quote() -> None:
    closing = build_closing_finalization(
        _pick(),
        _fixture(),
        finalized_at="2026-09-20T19:00:01+00:00",
        policy=OddsLifecyclePolicy(closing_max_age_seconds=1200),
        pair=None,
    )

    assert closing.outcome == "NO_VALID_QUOTE"
    assert closing.closing_observation_id is None
    assert closing.candidate_home_observation_id is None
    assert closing.candidate_away_observation_id is None
