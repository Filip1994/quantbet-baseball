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
from .moneyline_features import FEATURE_VERSION
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


def _shrunk_rate(
    *,
    contextual: float,
    overall: float,
    contextual_games: int,
    shrinkage_games: float,
) -> float:
    weight = contextual_games / (contextual_games + shrinkage_games)
    return weight * contextual + (1.0 - weight) * overall


def _pregame_context_status(features: dict[str, Any]) -> str:
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
    return "FULL_PREGAME_CONTEXT" if starters and lineups and bullpens else "LIMITED_CONTEXT"


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

    if snapshot.feature_version != FEATURE_VERSION:
        raise EvidenceError(
            f"baseline requires feature_version={FEATURE_VERSION}"
        )
    if not math.isfinite(shrinkage_games) or shrinkage_games <= 0:
        raise ValueError("shrinkage_games must be positive and finite")

    features = dict(snapshot.features)
    for name in _REQUIRED_RATE_FEATURES:
        _number(features, name, positive=True)
    for name in _REQUIRED_SAMPLE_FEATURES:
        _sample_games(features, name)

    home_games = _sample_games(features, "home_context_sample_games")
    away_games = _sample_games(features, "away_context_sample_games")

    home_offense = _shrunk_rate(
        contextual=_number(features, "home_context_runs_per_game", positive=True),
        overall=_number(features, "home_overall_runs_per_game", positive=True),
        contextual_games=home_games,
        shrinkage_games=shrinkage_games,
    )
    home_defense = _shrunk_rate(
        contextual=_number(
            features,
            "home_context_runs_allowed_per_game",
            positive=True,
        ),
        overall=_number(
            features,
            "home_overall_runs_allowed_per_game",
            positive=True,
        ),
        contextual_games=home_games,
        shrinkage_games=shrinkage_games,
    )
    away_offense = _shrunk_rate(
        contextual=_number(features, "away_context_runs_per_game", positive=True),
        overall=_number(features, "away_overall_runs_per_game", positive=True),
        contextual_games=away_games,
        shrinkage_games=shrinkage_games,
    )
    away_defense = _shrunk_rate(
        contextual=_number(
            features,
            "away_context_runs_allowed_per_game",
            positive=True,
        ),
        overall=_number(
            features,
            "away_overall_runs_allowed_per_game",
            positive=True,
        ),
        contextual_games=away_games,
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
        home_expected_runs=home_expected_runs,
        away_expected_runs=away_expected_runs,
        home_probability=home_probability,
        away_probability=away_probability,
        home_offense_rate=home_offense,
        away_offense_rate=away_offense,
        home_defense_rate=home_defense,
        away_defense_rate=away_defense,
        minimum_context_games=min(home_games, away_games),
        shrinkage_games=shrinkage_games,
        context_status=_pregame_context_status(features),
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
