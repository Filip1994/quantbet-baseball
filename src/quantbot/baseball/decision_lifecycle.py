"""Moneyline decision lifecycle facts for QuantBet Baseball."""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from .evidence import EvidenceError, OddsObservation
from .market import devig_two_way
from .value import edge, expected_value_per_unit, fair_decimal_odds

_PREDICTION_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/model-prediction/v1",
)
_EVALUATION_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/value-evaluation/v1",
)
_VERIFICATION_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/final-quote-verification/v1",
)
_PICK_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/registered-pick/v1",
)


def _timestamp(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise EvidenceError(f"{field} must be a non-empty ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise EvidenceError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{field} must be timezone-aware")
    return parsed


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{field} must be non-empty")
    return value


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise EvidenceError(f"{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        raise EvidenceError(f"{field} must be finite")
    return number


def _probability(value: Any, field: str) -> float:
    probability = _finite(value, field)
    if not 0.0 < probability < 1.0:
        raise EvidenceError(f"{field} must be between 0 and 1")
    return probability


def _uuid(namespace: uuid.UUID, identity: dict[str, Any]) -> str:
    canonical = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return str(uuid.uuid5(namespace, canonical))


def canonical_lifecycle_json(
    record: ModelPrediction
    | MoneylineEvaluation
    | FinalQuoteVerification
    | RegisteredPick,
) -> str:
    return json.dumps(
        asdict(record),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


@dataclass(frozen=True, slots=True)
class ModelPrediction:
    prediction_id: str
    game_id: str
    model_version: str
    feature_snapshot_ref: str
    source_data_cutoff_at: str
    predicted_at: str
    home_probability: float
    away_probability: float
    uncertainty_metric: float
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field in (
            "prediction_id",
            "game_id",
            "model_version",
            "feature_snapshot_ref",
            "schema_version",
        ):
            _nonempty(getattr(self, field), field)
        cutoff = _timestamp(self.source_data_cutoff_at, "source_data_cutoff_at")
        predicted = _timestamp(self.predicted_at, "predicted_at")
        if cutoff > predicted:
            raise EvidenceError("source_data_cutoff_at cannot follow predicted_at")
        home = _probability(self.home_probability, "home_probability")
        away = _probability(self.away_probability, "away_probability")
        if not math.isclose(home + away, 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise EvidenceError("model probabilities must sum to 1")
        if _finite(self.uncertainty_metric, "uncertainty_metric") < 0:
            raise EvidenceError("uncertainty_metric must be non-negative")


def build_model_prediction(
    *,
    game_id: str,
    model_version: str,
    feature_snapshot_ref: str,
    source_data_cutoff_at: str,
    predicted_at: str,
    home_probability: float,
    away_probability: float,
    uncertainty_metric: float,
) -> ModelPrediction:
    identity = {
        "game_id": game_id,
        "model_version": model_version,
        "feature_snapshot_ref": feature_snapshot_ref,
        "source_data_cutoff_at": source_data_cutoff_at,
        "predicted_at": predicted_at,
        "home_probability": home_probability,
        "away_probability": away_probability,
        "uncertainty_metric": uncertainty_metric,
    }
    return ModelPrediction(
        prediction_id=_uuid(_PREDICTION_NAMESPACE, identity),
        **identity,
    )


@dataclass(frozen=True, slots=True)
class MoneylineEvaluation:
    evaluation_id: str
    prediction_id: str
    game_id: str
    bookmaker: str
    home_observation_id: str
    away_observation_id: str
    selected_observation_id: str
    selection: str
    stage: str
    evaluated_at: str
    quote_observed_at: str
    quote_age_seconds: float
    selected_odds: float
    market_probability: float
    model_probability: float
    fair_decimal_odds: float
    edge: float
    expected_value_per_unit: float
    uncertainty_metric: float
    min_edge: float
    min_expected_value: float
    outcome: str
    reason_code: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field in (
            "evaluation_id",
            "prediction_id",
            "game_id",
            "bookmaker",
            "home_observation_id",
            "away_observation_id",
            "selected_observation_id",
            "reason_code",
            "schema_version",
        ):
            _nonempty(getattr(self, field), field)
        if self.selection not in {"home", "away"}:
            raise EvidenceError("selection must be home or away")
        if self.stage not in {"PRELIMINARY", "FINAL"}:
            raise EvidenceError("stage is unsupported")
        if self.outcome not in {"CANDIDATE", "PASS"}:
            raise EvidenceError("outcome is unsupported")
        evaluated = _timestamp(self.evaluated_at, "evaluated_at")
        observed = _timestamp(self.quote_observed_at, "quote_observed_at")
        if observed > evaluated:
            raise EvidenceError("quote cannot be observed after evaluation")
        if _finite(self.quote_age_seconds, "quote_age_seconds") < 0:
            raise EvidenceError("quote_age_seconds must be non-negative")
        if _finite(self.selected_odds, "selected_odds") <= 1.0:
            raise EvidenceError("selected_odds must be greater than 1")
        _probability(self.market_probability, "market_probability")
        _probability(self.model_probability, "model_probability")
        if _finite(self.fair_decimal_odds, "fair_decimal_odds") <= 1.0:
            raise EvidenceError("fair_decimal_odds must be greater than 1")
        _finite(self.edge, "edge")
        _finite(self.expected_value_per_unit, "expected_value_per_unit")
        if _finite(self.uncertainty_metric, "uncertainty_metric") < 0:
            raise EvidenceError("uncertainty_metric must be non-negative")
        if _finite(self.min_edge, "min_edge") < 0:
            raise EvidenceError("min_edge must be non-negative")
        _finite(self.min_expected_value, "min_expected_value")
        selected = (
            self.home_observation_id if self.selection == "home" else self.away_observation_id
        )
        if self.selected_observation_id != selected:
            raise EvidenceError("selected observation does not match selection")


def _validate_moneyline_pair(
    home: OddsObservation,
    away: OddsObservation,
) -> tuple[float, float]:
    if home.market_family != "moneyline" or away.market_family != "moneyline":
        raise EvidenceError("moneyline evaluation requires moneyline observations")
    if home.selection != "home" or away.selection != "away":
        raise EvidenceError("moneyline pair must be home and away")
    for field in ("game_id", "bookmaker", "observed_at", "kickoff_at"):
        if getattr(home, field) != getattr(away, field):
            raise EvidenceError(f"moneyline pair mismatch: {field}")
    if home.market_status != "open" or away.market_status != "open":
        raise EvidenceError("moneyline pair must be open")
    normalized = devig_two_way(
        1.0 / home.decimal_odds,
        1.0 / away.decimal_odds,
    )
    if normalized is None:
        raise EvidenceError("moneyline pair cannot be de-vigged")
    return normalized


def build_moneyline_evaluation(
    prediction: ModelPrediction,
    home: OddsObservation,
    away: OddsObservation,
    *,
    selection: str,
    stage: str,
    evaluated_at: str,
    min_edge: float,
    min_expected_value: float,
    max_uncertainty: float,
    max_quote_age_seconds: float,
) -> MoneylineEvaluation:
    home_market, away_market = _validate_moneyline_pair(home, away)
    if prediction.game_id != home.game_id:
        raise EvidenceError("prediction and market pair game mismatch")
    if selection not in {"home", "away"}:
        raise EvidenceError("selection must be home or away")
    if stage not in {"PRELIMINARY", "FINAL"}:
        raise EvidenceError("stage is unsupported")

    evaluated = _timestamp(evaluated_at, "evaluated_at")
    observed = _timestamp(home.observed_at, "quote_observed_at")
    kickoff = _timestamp(home.kickoff_at, "kickoff_at")
    if evaluated >= kickoff:
        raise EvidenceError("evaluation must occur before kickoff")
    quote_age = (evaluated - observed).total_seconds()
    if quote_age < 0:
        raise EvidenceError("quote cannot be from the future")

    min_edge_value = _finite(min_edge, "min_edge")
    min_ev_value = _finite(min_expected_value, "min_expected_value")
    max_uncertainty_value = _finite(max_uncertainty, "max_uncertainty")
    max_age_value = _finite(max_quote_age_seconds, "max_quote_age_seconds")
    if min_edge_value < 0 or max_uncertainty_value < 0 or max_age_value < 0:
        raise EvidenceError("policy limits must be non-negative")

    selected_observation = home if selection == "home" else away
    market_probability = home_market if selection == "home" else away_market
    model_probability = (
        prediction.home_probability
        if selection == "home"
        else prediction.away_probability
    )
    fair = fair_decimal_odds(model_probability)
    candidate_edge = edge(model_probability, market_probability)
    candidate_ev = expected_value_per_unit(
        model_probability,
        selected_observation.decimal_odds,
    )
    if fair is None or candidate_edge is None or candidate_ev is None:
        raise EvidenceError("valuation could not be calculated")

    outcome = "CANDIDATE"
    reason_code = "VALUE_AND_GATES_PASSED"
    if quote_age > max_age_value:
        outcome, reason_code = "PASS", "STALE_QUOTE"
    elif prediction.uncertainty_metric > max_uncertainty_value:
        outcome, reason_code = "PASS", "UNCERTAINTY_GATE_NOT_MET"
    elif candidate_edge < min_edge_value and not math.isclose(
        candidate_edge,
        min_edge_value,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        outcome, reason_code = "PASS", "EDGE_BELOW_THRESHOLD"
    elif candidate_ev < min_ev_value and not math.isclose(
        candidate_ev,
        min_ev_value,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        outcome, reason_code = "PASS", "EXPECTED_VALUE_BELOW_THRESHOLD"

    identity = {
        "prediction_id": prediction.prediction_id,
        "game_id": prediction.game_id,
        "bookmaker": home.bookmaker,
        "home_observation_id": home.observation_id,
        "away_observation_id": away.observation_id,
        "selected_observation_id": selected_observation.observation_id,
        "selection": selection,
        "stage": stage,
        "evaluated_at": evaluated_at,
        "min_edge": min_edge_value,
        "min_expected_value": min_ev_value,
        "max_uncertainty": max_uncertainty_value,
        "max_quote_age_seconds": max_age_value,
    }
    return MoneylineEvaluation(
        evaluation_id=_uuid(_EVALUATION_NAMESPACE, identity),
        prediction_id=prediction.prediction_id,
        game_id=prediction.game_id,
        bookmaker=home.bookmaker,
        home_observation_id=home.observation_id,
        away_observation_id=away.observation_id,
        selected_observation_id=selected_observation.observation_id,
        selection=selection,
        stage=stage,
        evaluated_at=evaluated_at,
        quote_observed_at=home.observed_at,
        quote_age_seconds=quote_age,
        selected_odds=selected_observation.decimal_odds,
        market_probability=market_probability,
        model_probability=model_probability,
        fair_decimal_odds=fair,
        edge=candidate_edge,
        expected_value_per_unit=candidate_ev,
        uncertainty_metric=prediction.uncertainty_metric,
        min_edge=min_edge_value,
        min_expected_value=min_ev_value,
        outcome=outcome,
        reason_code=reason_code,
    )


def build_moneyline_pair_evaluations(
    prediction: ModelPrediction,
    home: OddsObservation,
    away: OddsObservation,
    *,
    stage: str,
    evaluated_at: str,
    min_edge: float,
    min_expected_value: float,
    max_uncertainty: float,
    max_quote_age_seconds: float,
) -> tuple[MoneylineEvaluation, MoneylineEvaluation]:
    return (
        build_moneyline_evaluation(
            prediction,
            home,
            away,
            selection="home",
            stage=stage,
            evaluated_at=evaluated_at,
            min_edge=min_edge,
            min_expected_value=min_expected_value,
            max_uncertainty=max_uncertainty,
            max_quote_age_seconds=max_quote_age_seconds,
        ),
        build_moneyline_evaluation(
            prediction,
            home,
            away,
            selection="away",
            stage=stage,
            evaluated_at=evaluated_at,
            min_edge=min_edge,
            min_expected_value=min_expected_value,
            max_uncertainty=max_uncertainty,
            max_quote_age_seconds=max_quote_age_seconds,
        ),
    )


def select_best_candidate(
    evaluations: tuple[MoneylineEvaluation, ...],
) -> MoneylineEvaluation | None:
    eligible = [item for item in evaluations if item.outcome == "CANDIDATE"]
    if not eligible:
        return None
    return max(
        eligible,
        key=lambda item: (item.expected_value_per_unit, item.edge, item.selected_odds),
    )


@dataclass(frozen=True, slots=True)
class FinalQuoteVerification:
    verification_id: str
    preliminary_evaluation_id: str
    game_id: str
    bookmaker: str
    selection: str
    requested_at: str
    status: str
    reason_codes: tuple[str, ...]
    returned_home_observation_id: str | None
    returned_away_observation_id: str | None
    final_evaluation_id: str | None
    decided_at: str | None
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field in (
            "verification_id",
            "preliminary_evaluation_id",
            "game_id",
            "bookmaker",
            "schema_version",
        ):
            _nonempty(getattr(self, field), field)
        if self.selection not in {"home", "away"}:
            raise EvidenceError("verification selection is unsupported")
        if self.status not in {"REQUESTED", "READY", "REJECTED"}:
            raise EvidenceError("verification status is unsupported")
        requested = _timestamp(self.requested_at, "requested_at")
        pair_complete = (
            self.returned_home_observation_id is not None
            and self.returned_away_observation_id is not None
        )
        pair_empty = (
            self.returned_home_observation_id is None
            and self.returned_away_observation_id is None
        )
        if not pair_complete and not pair_empty:
            raise EvidenceError("verification quote pair must be complete")
        if self.status == "REQUESTED":
            if (
                self.reason_codes
                or not pair_empty
                or self.final_evaluation_id is not None
                or self.decided_at is not None
            ):
                raise EvidenceError("requested verification has terminal fields")
        elif self.status == "READY":
            if (
                self.reason_codes
                or not pair_complete
                or self.final_evaluation_id is None
                or self.decided_at is None
            ):
                raise EvidenceError("ready verification is incomplete")
        else:
            if not self.reason_codes or self.decided_at is None:
                raise EvidenceError("rejected verification requires reasons")
        if self.decided_at is not None:
            decided = _timestamp(self.decided_at, "decided_at")
            if decided < requested:
                raise EvidenceError("verification cannot finish before request")


def requested_verification(
    preliminary: MoneylineEvaluation,
    *,
    requested_at: str,
) -> FinalQuoteVerification:
    if preliminary.stage != "PRELIMINARY" or preliminary.outcome != "CANDIDATE":
        raise EvidenceError("only preliminary candidates can request final verification")
    identity = {"preliminary_evaluation_id": preliminary.evaluation_id}
    return FinalQuoteVerification(
        verification_id=_uuid(_VERIFICATION_NAMESPACE, identity),
        preliminary_evaluation_id=preliminary.evaluation_id,
        game_id=preliminary.game_id,
        bookmaker=preliminary.bookmaker,
        selection=preliminary.selection,
        requested_at=requested_at,
        status="REQUESTED",
        reason_codes=(),
        returned_home_observation_id=None,
        returned_away_observation_id=None,
        final_evaluation_id=None,
        decided_at=None,
    )


def ready_verification(
    requested: FinalQuoteVerification,
    *,
    home: OddsObservation,
    away: OddsObservation,
    final_evaluation: MoneylineEvaluation,
    decided_at: str,
) -> FinalQuoteVerification:
    if requested.status != "REQUESTED":
        raise EvidenceError("verification is already terminal")
    _validate_moneyline_pair(home, away)
    if (
        final_evaluation.stage != "FINAL"
        or final_evaluation.outcome != "CANDIDATE"
        or final_evaluation.game_id != requested.game_id
        or final_evaluation.bookmaker != requested.bookmaker
        or final_evaluation.selection != requested.selection
        or final_evaluation.home_observation_id != home.observation_id
        or final_evaluation.away_observation_id != away.observation_id
    ):
        raise EvidenceError("final evaluation does not match verification request")
    return FinalQuoteVerification(
        verification_id=requested.verification_id,
        preliminary_evaluation_id=requested.preliminary_evaluation_id,
        game_id=requested.game_id,
        bookmaker=requested.bookmaker,
        selection=requested.selection,
        requested_at=requested.requested_at,
        status="READY",
        reason_codes=(),
        returned_home_observation_id=home.observation_id,
        returned_away_observation_id=away.observation_id,
        final_evaluation_id=final_evaluation.evaluation_id,
        decided_at=decided_at,
    )


def rejected_verification(
    requested: FinalQuoteVerification,
    *,
    reason_codes: tuple[str, ...],
    decided_at: str,
    home: OddsObservation | None = None,
    away: OddsObservation | None = None,
    final_evaluation: MoneylineEvaluation | None = None,
) -> FinalQuoteVerification:
    if requested.status != "REQUESTED":
        raise EvidenceError("verification is already terminal")
    if not reason_codes:
        raise EvidenceError("rejection requires at least one reason")
    if (home is None) != (away is None):
        raise EvidenceError("rejection quote pair must be complete")
    if home is not None and away is not None:
        _validate_moneyline_pair(home, away)
    if final_evaluation is not None and (
        final_evaluation.stage != "FINAL"
        or final_evaluation.game_id != requested.game_id
        or final_evaluation.bookmaker != requested.bookmaker
        or final_evaluation.selection != requested.selection
    ):
        raise EvidenceError("rejected final evaluation does not match request")
    return FinalQuoteVerification(
        verification_id=requested.verification_id,
        preliminary_evaluation_id=requested.preliminary_evaluation_id,
        game_id=requested.game_id,
        bookmaker=requested.bookmaker,
        selection=requested.selection,
        requested_at=requested.requested_at,
        status="REJECTED",
        reason_codes=tuple(reason_codes),
        returned_home_observation_id=None if home is None else home.observation_id,
        returned_away_observation_id=None if away is None else away.observation_id,
        final_evaluation_id=None if final_evaluation is None else final_evaluation.evaluation_id,
        decided_at=decided_at,
    )


@dataclass(frozen=True, slots=True)
class RegisteredPick:
    pick_id: str
    verification_id: str
    final_evaluation_id: str
    prediction_id: str
    game_id: str
    market_family: str
    selection: str
    bookmaker: str
    entry_observation_id: str
    entry_odds: float
    model_probability: float
    market_probability: float
    fair_decimal_odds: float
    edge: float
    expected_value_per_unit: float
    uncertainty_metric: float
    model_version: str
    feature_snapshot_ref: str
    source_data_cutoff_at: str
    kickoff_at: str
    registered_at: str
    paper_mode: bool
    state: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field in (
            "pick_id",
            "verification_id",
            "final_evaluation_id",
            "prediction_id",
            "game_id",
            "bookmaker",
            "entry_observation_id",
            "model_version",
            "feature_snapshot_ref",
            "schema_version",
        ):
            _nonempty(getattr(self, field), field)
        if self.market_family != "moneyline":
            raise EvidenceError("registered pick market must be moneyline")
        if self.selection not in {"home", "away"}:
            raise EvidenceError("registered pick selection is unsupported")
        if self.state != "REGISTERED":
            raise EvidenceError("registered pick state is invalid")
        if self.paper_mode is not True:
            raise EvidenceError("this project only registers paper picks")
        if _finite(self.entry_odds, "entry_odds") <= 1.0:
            raise EvidenceError("entry_odds must be greater than 1")
        _probability(self.model_probability, "model_probability")
        _probability(self.market_probability, "market_probability")
        if _finite(self.fair_decimal_odds, "fair_decimal_odds") <= 1.0:
            raise EvidenceError("fair_decimal_odds must be greater than 1")
        _finite(self.edge, "edge")
        _finite(self.expected_value_per_unit, "expected_value_per_unit")
        if _finite(self.uncertainty_metric, "uncertainty_metric") < 0:
            raise EvidenceError("uncertainty_metric must be non-negative")
        cutoff = _timestamp(self.source_data_cutoff_at, "source_data_cutoff_at")
        kickoff = _timestamp(self.kickoff_at, "kickoff_at")
        registered = _timestamp(self.registered_at, "registered_at")
        if cutoff > registered:
            raise EvidenceError("source data cutoff cannot follow registration")
        if registered >= kickoff:
            raise EvidenceError("pick must be registered before kickoff")


def build_registered_pick(
    *,
    verification: FinalQuoteVerification,
    final_evaluation: MoneylineEvaluation,
    prediction: ModelPrediction,
    entry_observation: OddsObservation,
    registered_at: str,
) -> RegisteredPick:
    if verification.status != "READY":
        raise EvidenceError("registered pick requires ready final verification")
    if (
        verification.final_evaluation_id != final_evaluation.evaluation_id
        or final_evaluation.prediction_id != prediction.prediction_id
        or final_evaluation.outcome != "CANDIDATE"
        or final_evaluation.stage != "FINAL"
        or entry_observation.observation_id != final_evaluation.selected_observation_id
        or entry_observation.game_id != verification.game_id
        or entry_observation.bookmaker != verification.bookmaker
        or entry_observation.selection != verification.selection
    ):
        raise EvidenceError("registration provenance mismatch")
    identity = {"verification_id": verification.verification_id}
    return RegisteredPick(
        pick_id=_uuid(_PICK_NAMESPACE, identity),
        verification_id=verification.verification_id,
        final_evaluation_id=final_evaluation.evaluation_id,
        prediction_id=prediction.prediction_id,
        game_id=verification.game_id,
        market_family="moneyline",
        selection=verification.selection,
        bookmaker=verification.bookmaker,
        entry_observation_id=entry_observation.observation_id,
        entry_odds=final_evaluation.selected_odds,
        model_probability=final_evaluation.model_probability,
        market_probability=final_evaluation.market_probability,
        fair_decimal_odds=final_evaluation.fair_decimal_odds,
        edge=final_evaluation.edge,
        expected_value_per_unit=final_evaluation.expected_value_per_unit,
        uncertainty_metric=final_evaluation.uncertainty_metric,
        model_version=prediction.model_version,
        feature_snapshot_ref=prediction.feature_snapshot_ref,
        source_data_cutoff_at=prediction.source_data_cutoff_at,
        kickoff_at=entry_observation.kickoff_at,
        registered_at=registered_at,
        paper_mode=True,
        state="REGISTERED",
    )
