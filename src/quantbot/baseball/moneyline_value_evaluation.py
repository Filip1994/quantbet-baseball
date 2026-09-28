"""Bounded, restart-safe preliminary Moneyline value evaluation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from .bookmakers import PLAYABLE_BOOKMAKERS
from .decision_lifecycle import (
    ModelPrediction,
    MoneylineEvaluation,
    build_moneyline_pair_evaluations,
)
from .evidence import EvidenceError, OddsObservation


class EvaluationRepository(Protocol):
    def due_predictions_for_evaluation(
        self,
        *,
        as_of: datetime,
        horizon_minutes: int,
        limit: int,
    ) -> tuple[ModelPrediction, ...]: ...

    def latest_moneyline_pair(
        self,
        game_id: str,
        bookmaker: str,
        *,
        as_of: datetime,
        limit: int = 100,
    ) -> tuple[OddsObservation, OddsObservation] | None: ...

    def evaluation_pair_exists(
        self,
        *,
        prediction_id: str,
        bookmaker: str,
        home_observation_id: str,
        away_observation_id: str,
        stage: str,
    ) -> bool: ...

    def append_evaluation(self, record: MoneylineEvaluation) -> bool: ...


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)


def materialize_due_moneyline_evaluations(
    repository: EvaluationRepository,
    *,
    now: datetime,
    horizon_minutes: int = 360,
    max_games: int = 1,
    min_edge: float = 0.02,
    min_expected_value: float = 0.0,
    max_uncertainty: float = 0.05,
    max_quote_age_seconds: float = 900.0,
) -> dict[str, int | str]:
    """Evaluate bounded predictions using already-stored market evidence."""

    if horizon_minutes < 1:
        raise ValueError("horizon_minutes must be positive")
    if max_games < 1:
        raise ValueError("max_games must be positive")
    if min_edge < 0:
        raise ValueError("min_edge must be non-negative")
    if max_uncertainty < 0:
        raise ValueError("max_uncertainty must be non-negative")
    if max_quote_age_seconds < 0:
        raise ValueError("max_quote_age_seconds must be non-negative")

    current = _utc(now)
    predictions = repository.due_predictions_for_evaluation(
        as_of=current,
        horizon_minutes=horizon_minutes,
        limit=max_games,
    )
    result: dict[str, int | str] = {
        "status": "NO_DUE_PREDICTIONS",
        "predictions_seen": len(predictions),
        "games_considered": 0,
        "bookmaker_pairs_seen": 0,
        "bookmaker_pairs_already_evaluated": 0,
        "bookmaker_pairs_missing": 0,
        "evaluations_inserted": 0,
        "candidate_evaluations": 0,
        "pass_evaluations": 0,
        "evaluation_failures": 0,
        "provider_calls": 0,
    }
    if not predictions:
        return result

    result["games_considered"] = len(predictions)
    for prediction in predictions:
        for bookmaker in PLAYABLE_BOOKMAKERS.values():
            pair = repository.latest_moneyline_pair(
                prediction.game_id,
                bookmaker,
                as_of=current,
            )
            if pair is None:
                result["bookmaker_pairs_missing"] = (
                    int(result["bookmaker_pairs_missing"]) + 1
                )
                continue

            home, away = pair
            result["bookmaker_pairs_seen"] = int(result["bookmaker_pairs_seen"]) + 1
            if repository.evaluation_pair_exists(
                prediction_id=prediction.prediction_id,
                bookmaker=home.bookmaker,
                home_observation_id=home.observation_id,
                away_observation_id=away.observation_id,
                stage="PRELIMINARY",
            ):
                result["bookmaker_pairs_already_evaluated"] = (
                    int(result["bookmaker_pairs_already_evaluated"]) + 1
                )
                continue

            try:
                evaluations = build_moneyline_pair_evaluations(
                    prediction,
                    home,
                    away,
                    stage="PRELIMINARY",
                    evaluated_at=current.isoformat(),
                    min_edge=min_edge,
                    min_expected_value=min_expected_value,
                    max_uncertainty=max_uncertainty,
                    max_quote_age_seconds=max_quote_age_seconds,
                )
            except EvidenceError:
                result["evaluation_failures"] = (
                    int(result["evaluation_failures"]) + 1
                )
                continue

            for evaluation in evaluations:
                if repository.append_evaluation(evaluation):
                    result["evaluations_inserted"] = (
                        int(result["evaluations_inserted"]) + 1
                    )
                if evaluation.outcome == "CANDIDATE":
                    result["candidate_evaluations"] = (
                        int(result["candidate_evaluations"]) + 1
                    )
                else:
                    result["pass_evaluations"] = int(result["pass_evaluations"]) + 1

    if int(result["evaluation_failures"]) > 0:
        result["status"] = "BLOCKED_EVALUATION"
    elif int(result["bookmaker_pairs_seen"]) == 0:
        result["status"] = "NO_MARKET_PAIR"
    elif int(result["evaluations_inserted"]) == 0:
        result["status"] = "ALREADY_EVALUATED"
    else:
        result["status"] = "COMPLETE"
    return result
