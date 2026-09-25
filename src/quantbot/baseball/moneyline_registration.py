"""Moneyline preliminary evaluation and mandatory final-quote registration use cases."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from .api import BaseballAPIBudgetExceeded, BaseballAPIError
from .collector import compact_odds
from .decision_lifecycle import (
    FinalQuoteVerification,
    ModelPrediction,
    MoneylineEvaluation,
    RegisteredPick,
    build_moneyline_evaluation,
    build_moneyline_pair_evaluations,
    build_registered_pick,
    ready_verification,
    rejected_verification,
    requested_verification,
    select_best_candidate,
)
from .decision_repository import PostgreSQLMoneylineDecisionRepository
from .evidence import OddsObservation
from .ingestion import canonical_moneyline_observations


class FreshOddsClient(Protocol):
    def odds_with_receipt(self, game_id: int): ...


@dataclass(frozen=True, slots=True)
class MoneylineDecisionPolicy:
    min_edge: float = 0.02
    min_expected_value: float = 0.0
    max_uncertainty: float = 0.05
    preliminary_max_quote_age_seconds: float = 300.0
    final_max_quote_age_seconds: float = 120.0


@dataclass(frozen=True, slots=True)
class PreliminaryResult:
    evaluations: tuple[MoneylineEvaluation, MoneylineEvaluation]
    candidate: MoneylineEvaluation | None


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    verification: FinalQuoteVerification
    final_evaluation: MoneylineEvaluation | None
    pick: RegisteredPick | None


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _now(clock: Callable[[], datetime]) -> datetime:
    return _utc(clock(), "clock")


def _pregame_status(value: str) -> bool:
    normalized = " ".join(value.strip().casefold().replace("_", " ").split())
    return normalized in {"ns", "not started", "scheduled", "tbd"}


def _fresh_pair(
    records: tuple[OddsObservation, ...],
    bookmaker: str,
) -> tuple[OddsObservation, OddsObservation] | None:
    home = None
    away = None
    for record in records:
        if record.bookmaker != bookmaker:
            continue
        if record.selection == "home":
            home = record
        elif record.selection == "away":
            away = record
    if home is None or away is None:
        return None
    if home.observed_at != away.observed_at:
        return None
    return home, away


def evaluate_preliminary_moneyline(
    repository: PostgreSQLMoneylineDecisionRepository,
    prediction: ModelPrediction,
    *,
    bookmaker: str,
    evaluated_at: datetime,
    policy: MoneylineDecisionPolicy,
) -> PreliminaryResult | None:
    checked = _utc(evaluated_at, "evaluated_at")
    repository.append_prediction(prediction)
    pair = repository.latest_moneyline_pair(
        prediction.game_id,
        bookmaker,
        as_of=checked,
    )
    if pair is None:
        return None
    evaluations = build_moneyline_pair_evaluations(
        prediction,
        pair[0],
        pair[1],
        stage="PRELIMINARY",
        evaluated_at=checked.isoformat(),
        min_edge=policy.min_edge,
        min_expected_value=policy.min_expected_value,
        max_uncertainty=policy.max_uncertainty,
        max_quote_age_seconds=policy.preliminary_max_quote_age_seconds,
    )
    for evaluation in evaluations:
        repository.append_evaluation(evaluation)
    return PreliminaryResult(
        evaluations=evaluations,
        candidate=select_best_candidate(evaluations),
    )


def _reject(
    repository: PostgreSQLMoneylineDecisionRepository,
    requested: FinalQuoteVerification,
    *,
    reason: str,
    decided_at: datetime,
    home: OddsObservation | None = None,
    away: OddsObservation | None = None,
    final_evaluation: MoneylineEvaluation | None = None,
) -> RegistrationResult:
    rejected = rejected_verification(
        requested,
        reason_codes=(reason,),
        decided_at=decided_at.isoformat(),
        home=home,
        away=away,
        final_evaluation=final_evaluation,
    )
    stored = repository.save_terminal_verification(rejected)
    return RegistrationResult(stored, final_evaluation, None)


def _resume_ready(
    repository: PostgreSQLMoneylineDecisionRepository,
    verification: FinalQuoteVerification,
    *,
    registered_at: datetime,
) -> RegistrationResult:
    existing = repository.get_registered_pick_for_verification(
        verification.verification_id
    )
    if existing is not None:
        final = (
            None
            if verification.final_evaluation_id is None
            else repository.get_evaluation(verification.final_evaluation_id)
        )
        return RegistrationResult(verification, final, existing)

    if verification.final_evaluation_id is None:
        raise RuntimeError("READY verification is missing final evaluation")
    final = repository.get_evaluation(verification.final_evaluation_id)
    if final is None:
        raise RuntimeError("READY verification final evaluation does not resolve")
    prediction = repository.get_prediction(final.prediction_id)
    if prediction is None:
        raise RuntimeError("READY verification prediction does not resolve")
    entry = repository.get_observation(final.selected_observation_id)
    if entry is None:
        raise RuntimeError("READY verification entry quote does not resolve")
    pick = build_registered_pick(
        verification=verification,
        final_evaluation=final,
        prediction=prediction,
        entry_observation=entry,
        registered_at=registered_at.isoformat(),
    )
    repository.append_registered_pick(pick)
    return RegistrationResult(verification, final, pick)


def verify_and_register_moneyline(
    client: FreshOddsClient,
    repository: PostgreSQLMoneylineDecisionRepository,
    preliminary_evaluation_id: str,
    *,
    clock: Callable[[], datetime],
    policy: MoneylineDecisionPolicy,
) -> RegistrationResult:
    preliminary = repository.get_evaluation(preliminary_evaluation_id)
    if preliminary is None:
        raise LookupError(preliminary_evaluation_id)
    if preliminary.stage != "PRELIMINARY" or preliminary.outcome != "CANDIDATE":
        raise ValueError("final quote verification requires a preliminary candidate")

    requested_at = _now(clock)
    requested = requested_verification(
        preliminary,
        requested_at=requested_at.isoformat(),
    )
    claim = repository.begin_verification(requested)
    if claim.status == "REJECTED":
        final = (
            None
            if claim.final_evaluation_id is None
            else repository.get_evaluation(claim.final_evaluation_id)
        )
        return RegistrationResult(claim, final, None)
    if claim.status == "READY":
        return _resume_ready(
            repository,
            claim,
            registered_at=_now(clock),
        )

    prediction = repository.get_prediction(preliminary.prediction_id)
    if prediction is None:
        return _reject(
            repository,
            claim,
            reason="PREDICTION_NOT_FOUND",
            decided_at=_now(clock),
        )

    fixture = repository.latest_fixture_observation(
        preliminary.game_id,
        as_of=requested_at,
    )
    if fixture is None:
        return _reject(
            repository,
            claim,
            reason="FIXTURE_NOT_FOUND",
            decided_at=_now(clock),
        )
    if not _pregame_status(fixture.provider_status):
        return _reject(
            repository,
            claim,
            reason="FIXTURE_STATUS_NOT_PREGAME",
            decided_at=_now(clock),
        )

    kickoff = datetime.fromisoformat(fixture.kickoff_at).astimezone(UTC)
    if requested_at >= kickoff:
        return _reject(
            repository,
            claim,
            reason="KICKOFF_REACHED",
            decided_at=_now(clock),
        )

    try:
        provider_game_id = int(fixture.provider_game_id)
        odds, receipt = client.odds_with_receipt(provider_game_id)
    except BaseballAPIBudgetExceeded:
        return _reject(
            repository,
            claim,
            reason="API_BUDGET_EXHAUSTED",
            decided_at=_now(clock),
        )
    except (BaseballAPIError, TypeError, ValueError):
        return _reject(
            repository,
            claim,
            reason="FINAL_QUOTE_API_ERROR",
            decided_at=_now(clock),
        )

    compact = compact_odds(odds)
    snapshot = {
        "captured_at": receipt.captured_at,
        "game_id": fixture.provider_game_id,
        "kickoff": fixture.kickoff_at,
        "league": fixture.league,
        "home": fixture.home_team_name,
        "away": fixture.away_team_name,
        "odds": compact,
    }
    records = canonical_moneyline_observations(snapshot, receipt)
    repository.append_observations(records)
    pair = _fresh_pair(records, preliminary.bookmaker)
    if pair is None:
        return _reject(
            repository,
            claim,
            reason="EXACT_BOOKMAKER_PAIR_UNAVAILABLE",
            decided_at=_now(clock),
        )

    evaluated_at = _now(clock)
    final = build_moneyline_evaluation(
        prediction,
        pair[0],
        pair[1],
        selection=preliminary.selection,
        stage="FINAL",
        evaluated_at=evaluated_at.isoformat(),
        min_edge=policy.min_edge,
        min_expected_value=policy.min_expected_value,
        max_uncertainty=policy.max_uncertainty,
        max_quote_age_seconds=policy.final_max_quote_age_seconds,
    )
    repository.append_evaluation(final)

    if final.outcome != "CANDIDATE":
        return _reject(
            repository,
            claim,
            reason=f"FINAL_{final.reason_code}",
            decided_at=_now(clock),
            home=pair[0],
            away=pair[1],
            final_evaluation=final,
        )

    decided_at = _now(clock)
    ready = ready_verification(
        claim,
        home=pair[0],
        away=pair[1],
        final_evaluation=final,
        decided_at=decided_at.isoformat(),
    )
    stored = repository.save_terminal_verification(ready)
    return _resume_ready(
        repository,
        stored,
        registered_at=_now(clock),
    )
