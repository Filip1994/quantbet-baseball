from datetime import UTC, datetime

from quantbot.baseball.decision_lifecycle import build_model_prediction
from quantbot.baseball.evidence import OddsObservation
from quantbot.baseball.moneyline_value_evaluation import (
    materialize_due_moneyline_evaluations,
)


def _prediction():
    return build_model_prediction(
        game_id="123",
        model_version="team-strength-poisson-baseline-v1",
        feature_snapshot_ref="feature-123",
        source_data_cutoff_at="2030-07-04T16:00:00+00:00",
        predicted_at="2030-07-04T16:01:00+00:00",
        home_probability=0.55,
        away_probability=0.45,
        uncertainty_metric=0.025,
    )


def _obs(observation_id: str, selection: str, odds: float):
    return OddsObservation(
        observation_id=observation_id,
        game_id="123",
        market_family="moneyline",
        line=None,
        selection=selection,
        bookmaker="bet365",
        decimal_odds=odds,
        raw_price=str(odds),
        observed_at="2030-07-04T16:04:00+00:00",
        retrieved_at="2030-07-04T16:04:00+00:00",
        source_payload_ref=f"s3://raw/{observation_id}.json",
        source_payload_checksum="a" * 64,
        schema_version="1.0",
        market_status="open",
        kickoff_at="2030-07-04T19:00:00+00:00",
    )


class _Repo:
    def __init__(self):
        self.prediction = _prediction()
        self.evaluations = []

    def due_predictions_for_evaluation(self, *, as_of, horizon_minutes, limit):
        assert horizon_minutes == 360
        assert limit == 1
        return (self.prediction,)

    def latest_moneyline_pair(self, game_id, bookmaker, *, as_of, limit=100):
        if bookmaker.casefold() != "bet365":
            return None
        return (
            _obs("00000000-0000-0000-0000-000000000001", "home", 2.10),
            _obs("00000000-0000-0000-0000-000000000002", "away", 1.80),
        )

    def evaluation_pair_exists(
        self,
        *,
        prediction_id,
        bookmaker,
        home_observation_id,
        away_observation_id,
        stage,
    ):
        return any(
            item.prediction_id == prediction_id
            and item.bookmaker.casefold() == bookmaker.casefold()
            and item.home_observation_id == home_observation_id
            and item.away_observation_id == away_observation_id
            and item.stage == stage
            for item in self.evaluations
        )

    def append_evaluation(self, record):
        if any(item.evaluation_id == record.evaluation_id for item in self.evaluations):
            return False
        self.evaluations.append(record)
        return True


def test_value_evaluation_materializer_is_bounded_and_restart_safe() -> None:
    repo = _Repo()
    now = datetime(2030, 7, 4, 16, 5, tzinfo=UTC)

    first = materialize_due_moneyline_evaluations(
        repo,
        now=now,
        horizon_minutes=360,
        max_games=1,
        min_edge=0.02,
        min_expected_value=0.0,
        max_uncertainty=0.05,
        max_quote_age_seconds=900,
    )
    second = materialize_due_moneyline_evaluations(
        repo,
        now=now,
        horizon_minutes=360,
        max_games=1,
        min_edge=0.02,
        min_expected_value=0.0,
        max_uncertainty=0.05,
        max_quote_age_seconds=900,
    )

    assert first["status"] == "COMPLETE"
    assert first["games_considered"] == 1
    assert first["bookmaker_pairs_seen"] == 1
    assert first["evaluations_inserted"] == 2
    assert first["candidate_evaluations"] == 1
    assert first["pass_evaluations"] == 1
    assert first["provider_calls"] == 0
    assert len(repo.evaluations) == 2

    assert second["status"] == "ALREADY_EVALUATED"
    assert second["bookmaker_pairs_already_evaluated"] == 1
    assert second["evaluations_inserted"] == 0
    assert len(repo.evaluations) == 2


def test_value_evaluation_reports_no_market_without_synthetic_rows() -> None:
    repo = _Repo()
    repo.latest_moneyline_pair = lambda *args, **kwargs: None
    result = materialize_due_moneyline_evaluations(
        repo,
        now=datetime(2030, 7, 4, 16, 5, tzinfo=UTC),
    )

    assert result["status"] == "NO_MARKET_PAIR"
    assert result["evaluations_inserted"] == 0
    assert len(repo.evaluations) == 0
