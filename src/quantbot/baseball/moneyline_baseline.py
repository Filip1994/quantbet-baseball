"""Transparent research-only Moneyline team-strength baseline.

This module is intentionally not wired to model_predictions or pick emission.
It establishes a deterministic probability benchmark that can be evaluated
chronologically before any claim of betting edge is allowed.
"""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from .evidence import EvidenceError
from .feature_snapshot import FeatureSnapshot
from .moneyline_features import CORE_FEATURE_VERSION, FEATURE_VERSION
from .run_model import poisson_moneyline_probabilities

MODEL_VERSION = "team-strength-poisson-baseline-v1"
_PROJECTION_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/team-strength-poisson-baseline/v1",
)

_REQUIRED_RATE_FEATURES = (
    "home_overall_runs_per_game",
    "home_context_runs_per_game",
    "home_overall_runs_allowed_per_game",
    "home_context_runs_allowed_per_game",
    "away_overall_runs_per_game",
    "away_context_runs_per_game",
    "away_overall_runs_allowed_per_game",
    "away_context_runs_allowed_per_game",
)
_REQUIRED_SAMPLE_FEATURES = (
    "home_context_sample_games",
    "away_context_sample_games",
)


def _number(features: dict[str, Any], name: str, *, positive: bool = False) -> float:
    value = features.get(name)
    if isinstance(value, bool):
        raise EvidenceError(f"{name} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{name} must be numeric") from exc
    if not math.isfinite(number):
        raise EvidenceError(f"{name} must be finite")
    if positive and number <= 0.0:
        raise EvidenceError(f"{name} must be positive")
    return number


def _sample_games(features: dict[str, Any], name: str) -> int:
    number = _number(features, name)
    if not number.is_integer() or number < 0:
        raise EvidenceError(f"{name} must be a non-negative integer")
    return int(number)


def _positive_rate(value: float, field: str) -> float:
    if isinstance(value, bool):
        raise EvidenceError(f"{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or number <= 0.0:
        raise EvidenceError(f"{field} must be positive and finite")
    return number


def _context_games(value: int, field: str) -> int:
    if isinstance(value, bool):
        raise EvidenceError(f"{field} must be a non-negative integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field} must be a non-negative integer") from exc
    if number != value or number < 0:
        raise EvidenceError(f"{field} must be a non-negative integer")
    return number


def _shrunk_rate(
    *,
    contextual: float,
    overall: float,
    contextual_games: int,
    shrinkage_games: float,
) -> float:
    weight = contextual_games / (contextual_games + shrinkage_games)
    return weight * contextual + (1.0 - weight) * overall


def _pregame_context_status(features: dict[str, Any], *, feature_version: str) -> str:
    if feature_version == CORE_FEATURE_VERSION:
        return "CORE_TEAM_STRENGTH_ONLY"
    starters = (
        features.get("home_starter_identified") is True
        and features.get("away_starter_identified") is True
    )
    lineups = (
        features.get("home_lineup_populated") is True
        and features.get("away_lineup_populated") is True
    )
    bullpens = (
        features.get("home_bullpen_state") == "PRESENT"
        and features.get("away_bullpen_state") == "PRESENT"
    )
    return (
        "FULL_PREGAME_CONTEXT"
        if starters and lineups and bullpens
        else "LIMITED_CONTEXT"
    )


@dataclass(frozen=True, slots=True)
class TeamStrengthRates:
    home_overall_runs_per_game: float
    home_context_runs_per_game: float
    home_overall_runs_allowed_per_game: float
    home_context_runs_allowed_per_game: float
    home_context_sample_games: int
    away_overall_runs_per_game: float
    away_context_runs_per_game: float
    away_overall_runs_allowed_per_game: float
    away_context_runs_allowed_per_game: float
    away_context_sample_games: int

    def __post_init__(self) -> None:
        for field in (
            "home_overall_runs_per_game",
            "home_context_runs_per_game",
            "home_overall_runs_allowed_per_game",
            "home_context_runs_allowed_per_game",
            "away_overall_runs_per_game",
            "away_context_runs_per_game",
            "away_overall_runs_allowed_per_game",
            "away_context_runs_allowed_per_game",
        ):
            _positive_rate(getattr(self, field), field)
        for field in (
            "home_context_sample_games",
            "away_context_sample_games",
        ):
            _context_games(getattr(self, field), field)


@dataclass(frozen=True, slots=True)
class TeamStrengthProbabilityCore:
    home_expected_runs: float
    away_expected_runs: float
    home_probability: float
    away_probability: float
    home_offense_rate: float
    away_offense_rate: float
    home_defense_rate: float
    away_defense_rate: float
    minimum_context_games: int
    shrinkage_games: float


def calculate_team_strength_probability(
    rates: TeamStrengthRates,
    *,
    shrinkage_games: float = 30.0,
) -> TeamStrengthProbabilityCore:
    """Apply the canonical team-strength baseline math to validated rates."""

    if not math.isfinite(shrinkage_games) or shrinkage_games <= 0:
        raise ValueError("shrinkage_games must be positive and finite")

    home_offense = _shrunk_rate(
        contextual=rates.home_context_runs_per_game,
        overall=rates.home_overall_runs_per_game,
        contextual_games=rates.home_context_sample_games,
        shrinkage_games=shrinkage_games,
    )
    home_defense = _shrunk_rate(
        contextual=rates.home_context_runs_allowed_per_game,
        overall=rates.home_overall_runs_allowed_per_game,
        contextual_games=rates.home_context_sample_games,
        shrinkage_games=shrinkage_games,
    )
    away_offense = _shrunk_rate(
        contextual=rates.away_context_runs_per_game,
        overall=rates.away_overall_runs_per_game,
        contextual_games=rates.away_context_sample_games,
        shrinkage_games=shrinkage_games,
    )
    away_defense = _shrunk_rate(
        contextual=rates.away_context_runs_allowed_per_game,
        overall=rates.away_overall_runs_allowed_per_game,
        contextual_games=rates.away_context_sample_games,
        shrinkage_games=shrinkage_games,
    )

    home_expected_runs = math.sqrt(home_offense * away_defense)
    away_expected_runs = math.sqrt(away_offense * home_defense)
    probabilities = poisson_moneyline_probabilities(
        home_expected_runs,
        away_expected_runs,
    )
    if probabilities is None:
        raise EvidenceError("baseline moneyline probabilities could not be calculated")
    home_probability, away_probability = probabilities

    return TeamStrengthProbabilityCore(
        home_expected_runs=home_expected_runs,
        away_expected_runs=away_expected_runs,
        home_probability=home_probability,
        away_probability=away_probability,
        home_offense_rate=home_offense,
        away_offense_rate=away_offense,
        home_defense_rate=home_defense,
        away_defense_rate=away_defense,
        minimum_context_games=min(
            rates.home_context_sample_games,
            rates.away_context_sample_games,
        ),
        shrinkage_games=shrinkage_games,
    )


@dataclass(frozen=True, slots=True)
class TeamStrengthMoneylineProjection:
    projection_id: str
    game_id: str
    feature_snapshot_id: str
    feature_version: str
    model_version: str
    projected_at: str
    home_expected_runs: float
    away_expected_runs: float
    home_probability: float
    away_probability: float
    home_offense_rate: float
    away_offense_rate: float
    home_defense_rate: float
    away_defense_rate: float
    minimum_context_games: int
    shrinkage_games: float
    context_status: str
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def project_team_strength_moneyline(
    snapshot: FeatureSnapshot,
    *,
    shrinkage_games: float = 30.0,
) -> TeamStrengthMoneylineProjection:
    """Project two-way win probability from compact team run-rate strength only.

    Home/away contextual rates are shrunk toward each team's overall rate.
    Expected runs use the geometric mean of the relevant offense and opponent
    run-allowance rates. Starter/lineup/bullpen state is reported as context
    quality but deliberately does not alter probability in this baseline.
    """

    if snapshot.feature_version not in {FEATURE_VERSION, CORE_FEATURE_VERSION}:
        raise EvidenceError(
            "baseline requires feature_version="
            f"{FEATURE_VERSION} or {CORE_FEATURE_VERSION}"
        )

    features = dict(snapshot.features)
    for name in _REQUIRED_RATE_FEATURES:
        _number(features, name, positive=True)
    for name in _REQUIRED_SAMPLE_FEATURES:
        _sample_games(features, name)

    rates = TeamStrengthRates(
        home_overall_runs_per_game=_number(
            features,
            "home_overall_runs_per_game",
            positive=True,
        ),
        home_context_runs_per_game=_number(
            features,
            "home_context_runs_per_game",
            positive=True,
        ),
        home_overall_runs_allowed_per_game=_number(
            features,
            "home_overall_runs_allowed_per_game",
            positive=True,
        ),
        home_context_runs_allowed_per_game=_number(
            features,
            "home_context_runs_allowed_per_game",
            positive=True,
        ),
        home_context_sample_games=_sample_games(
            features,
            "home_context_sample_games",
        ),
        away_overall_runs_per_game=_number(
            features,
            "away_overall_runs_per_game",
            positive=True,
        ),
        away_context_runs_per_game=_number(
            features,
            "away_context_runs_per_game",
            positive=True,
        ),
        away_overall_runs_allowed_per_game=_number(
            features,
            "away_overall_runs_allowed_per_game",
            positive=True,
        ),
        away_context_runs_allowed_per_game=_number(
            features,
            "away_context_runs_allowed_per_game",
            positive=True,
        ),
        away_context_sample_games=_sample_games(
            features,
            "away_context_sample_games",
        ),
    )
    core = calculate_team_strength_probability(
        rates,
        shrinkage_games=shrinkage_games,
    )

    identity = {
        "game_id": snapshot.game_id,
        "feature_snapshot_id": snapshot.snapshot_id,
        "model_version": MODEL_VERSION,
        "shrinkage_games": shrinkage_games,
    }
    canonical = json.dumps(
        identity,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    projection_id = str(uuid.uuid5(_PROJECTION_NAMESPACE, canonical))

    return TeamStrengthMoneylineProjection(
        projection_id=projection_id,
        game_id=snapshot.game_id,
        feature_snapshot_id=snapshot.snapshot_id,
        feature_version=snapshot.feature_version,
        model_version=MODEL_VERSION,
        projected_at=snapshot.generated_at,
        home_expected_runs=core.home_expected_runs,
        away_expected_runs=core.away_expected_runs,
        home_probability=core.home_probability,
        away_probability=core.away_probability,
        home_offense_rate=core.home_offense_rate,
        away_offense_rate=core.away_offense_rate,
        home_defense_rate=core.home_defense_rate,
        away_defense_rate=core.away_defense_rate,
        minimum_context_games=core.minimum_context_games,
        shrinkage_games=core.shrinkage_games,
        context_status=_pregame_context_status(
            features,
            feature_version=snapshot.feature_version,
        ),
    )


def canonical_team_strength_projection_json(
    projection: TeamStrengthMoneylineProjection,
) -> str:
    return json.dumps(
        projection.to_dict(),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
