"""Immutable point-in-time feature evidence for Baseball predictions."""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from .evidence import EvidenceError

_FEATURE_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/pregame-feature-snapshot/v1",
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


def _text(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise EvidenceError(f"{field} must be non-empty")
    return result


def _json_safe(value: Any, field: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise EvidenceError(f"{field} cannot contain non-finite numbers")
    if isinstance(value, dict):
        for key, child in value.items():
            _text(key, f"{field} key")
            _json_safe(child, f"{field}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _json_safe(child, f"{field}[{index}]")
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise EvidenceError(f"{field} contains a non-JSON value")


@dataclass(frozen=True, slots=True)
class FeatureSource:
    provider: str
    source_type: str
    observed_at: str
    available_at: str
    source_payload_ref: str
    source_payload_checksum: str
    feature_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in (
            "provider",
            "source_type",
            "source_payload_ref",
            "source_payload_checksum",
        ):
            _text(getattr(self, field), field)
        observed = _timestamp(self.observed_at, "observed_at")
        available = _timestamp(self.available_at, "available_at")
        if available < observed:
            raise EvidenceError("source available_at cannot precede observed_at")
        if len(self.source_payload_checksum) != 64 or any(
            char not in "0123456789abcdefABCDEF"
            for char in self.source_payload_checksum
        ):
            raise EvidenceError("source_payload_checksum must be SHA-256 hex")
        if not self.feature_paths:
            raise EvidenceError(
                "feature source must identify at least one feature path"
            )
        for path in self.feature_paths:
            _text(path, "feature_path")


@dataclass(frozen=True, slots=True)
class PregameFeatureSnapshot:
    feature_snapshot_id: str
    game_id: str
    feature_set_version: str
    source_data_cutoff_at: str
    generated_at: str
    kickoff_at: str
    features: dict[str, Any]
    sources: tuple[FeatureSource, ...]
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field in (
            "feature_snapshot_id",
            "game_id",
            "feature_set_version",
            "schema_version",
        ):
            _text(getattr(self, field), field)
        cutoff = _timestamp(self.source_data_cutoff_at, "source_data_cutoff_at")
        generated = _timestamp(self.generated_at, "generated_at")
        kickoff = _timestamp(self.kickoff_at, "kickoff_at")
        if cutoff > generated:
            raise EvidenceError("source data cutoff cannot follow snapshot generation")
        if generated >= kickoff:
            raise EvidenceError("feature snapshot must be generated before kickoff")
        if not isinstance(self.features, dict) or not self.features:
            raise EvidenceError("features must be a non-empty object")
        _json_safe(self.features, "features")
        if not self.sources:
            raise EvidenceError("feature snapshot requires source evidence")
        for source in self.sources:
            if _timestamp(source.available_at, "source.available_at") > cutoff:
                raise EvidenceError("feature source was not available by cutoff")

    @property
    def ref(self) -> str:
        return f"feature://pregame/{self.feature_snapshot_id}"

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["sources"] = [asdict(source) for source in self.sources]
        return value


def build_pregame_feature_snapshot(
    *,
    game_id: str,
    feature_set_version: str,
    source_data_cutoff_at: str,
    generated_at: str,
    kickoff_at: str,
    features: dict[str, Any],
    sources: tuple[FeatureSource, ...],
) -> PregameFeatureSnapshot:
    identity = {
        "game_id": game_id,
        "feature_set_version": feature_set_version,
        "source_data_cutoff_at": source_data_cutoff_at,
        "generated_at": generated_at,
        "kickoff_at": kickoff_at,
        "features": features,
        "sources": [asdict(source) for source in sources],
    }
    canonical = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return PregameFeatureSnapshot(
        feature_snapshot_id=str(uuid.uuid5(_FEATURE_NAMESPACE, canonical)),
        game_id=game_id,
        feature_set_version=feature_set_version,
        source_data_cutoff_at=source_data_cutoff_at,
        generated_at=generated_at,
        kickoff_at=kickoff_at,
        features=features,
        sources=sources,
    )


def canonical_feature_snapshot_json(record: PregameFeatureSnapshot) -> str:
    return json.dumps(
        record.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
