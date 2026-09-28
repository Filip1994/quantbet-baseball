"""Bounded, restart-safe materialization of baseline Moneyline predictions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from .decision_lifecycle import ModelPrediction, build_model_prediction
from .feature_snapshot import FeatureSnapshot
from .moneyline_baseline import MODEL_VERSION, project_team_strength_moneyline
from .moneyline_features import CORE_FEATURE_VERSION, FEATURE_VERSION


class PredictionFeatureRepository(Protocol):
    def due_for_prediction(
        self,
        *,
        feature_versions: tuple[str, ...],
        as_of: datetime,
        horizon_minutes: int,
        limit: int,
    ) -> tuple[FeatureSnapshot, ...]: ...


class PredictionDecisionRepository(Protocol):
    def get_prediction_for_feature_snapshot(
        self,
        *,
        model_version: str,
        feature_snapshot_ref: str,
    ) -> ModelPrediction | None: ...

    def append_prediction(self, record: ModelPrediction) -> bool: ...


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)


def uncertainty_proxy(minimum_context_games: int) -> float:
    """Return a transparent inverse-sample-size uncertainty proxy.

    This is deliberately not presented as a calibrated probability error.
    """

    if isinstance(minimum_context_games, bool) or minimum_context_games < 1:
        raise ValueError("minimum_context_games must be a positive integer")
    return 1.0 / float(minimum_context_games)


def materialize_due_baseline_predictions(
    feature_repository: PredictionFeatureRepository,
    decision_repository: PredictionDecisionRepository,
    *,
    now: datetime,
    horizon_minutes: int = 360,
    max_predictions: int = 1,
) -> dict[str, int | str]:
    """Persist a bounded number of baseline predictions from accepted features."""

    if horizon_minutes < 1:
        raise ValueError("horizon_minutes must be positive")
    if max_predictions < 1:
        raise ValueError("max_predictions must be positive")

    current = _utc(now)
    snapshots = feature_repository.due_for_prediction(
        feature_versions=(CORE_FEATURE_VERSION, FEATURE_VERSION),
        as_of=current,
        horizon_minutes=horizon_minutes,
        limit=max_predictions * 4,
    )
    result: dict[str, int | str] = {
        "status": "NO_DUE_FEATURES",
        "features_seen": len(snapshots),
        "already_predicted": 0,
        "predictions_considered": 0,
        "predictions_inserted": 0,
        "projection_failures": 0,
        "due_features_unprocessed": 0,
        "provider_calls": 0,
    }
    if not snapshots:
        return result

    selected: list[FeatureSnapshot] = []
    for snapshot in snapshots:
        existing = decision_repository.get_prediction_for_feature_snapshot(
            model_version=MODEL_VERSION,
            feature_snapshot_ref=snapshot.snapshot_id,
        )
        if existing is not None:
            result["already_predicted"] = int(result["already_predicted"]) + 1
            continue
        selected.append(snapshot)
        if len(selected) >= max_predictions:
            break

    result["predictions_considered"] = len(selected)
    for snapshot in selected:
        try:
            projection = project_team_strength_moneyline(snapshot)
            prediction = build_model_prediction(
                game_id=snapshot.game_id,
                model_version=projection.model_version,
                feature_snapshot_ref=snapshot.snapshot_id,
                source_data_cutoff_at=snapshot.source_data_cutoff_at,
                predicted_at=current.isoformat(),
                home_probability=projection.home_probability,
                away_probability=projection.away_probability,
                uncertainty_metric=uncertainty_proxy(
                    projection.minimum_context_games
                ),
            )
        except (ValueError, TypeError):
            result["projection_failures"] = int(result["projection_failures"]) + 1
            continue
        inserted = decision_repository.append_prediction(prediction)
        result["predictions_inserted"] = int(result["predictions_inserted"]) + int(
            inserted
        )

    remaining = max(
        0,
        len(snapshots)
        - int(result["already_predicted"])
        - int(result["predictions_considered"]),
    )
    result["due_features_unprocessed"] = remaining
    if int(result["projection_failures"]) > 0:
        result["status"] = "BLOCKED_PROJECTION"
    elif remaining > 0:
        result["status"] = "CAPACITY_LIMITED"
    else:
        result["status"] = "COMPLETE"
    return result
