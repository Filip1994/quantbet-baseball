"""Immutable point-in-time feature snapshots for Baseball model research."""

from __future__ import annotations

import json
import math
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from .evidence import EvidenceError

_FEATURE_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/feature-snapshot/v1",
)
_ALLOWED_SCALARS = (str, int, float, bool, type(None))


def _timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{field} must be timezone-aware")
    return parsed


def _nonempty(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise EvidenceError(f"{field} must be non-empty")
    return result


def _checksum(value: str) -> str:
    checksum = _nonempty(value, "source_payload_checksum")
    if len(checksum) != 64 or any(
        char not in "0123456789abcdefABCDEF" for char in checksum
    ):
        raise EvidenceError("source_payload_checksum must be a SHA-256 hex digest")
    return checksum


def _feature_scalar(value: Any, field: str) -> Any:
    if not isinstance(value, _ALLOWED_SCALARS):
        raise EvidenceError(f"{field} must be a JSON scalar or null")
    if isinstance(value, float) and not math.isfinite(value):
        raise EvidenceError(f"{field} must be finite")
    return value


@dataclass(frozen=True, slots=True)
class FeatureSource:
    source_name: str
    observed_at: str
    source_payload_ref: str
    source_payload_checksum: str
    field_names: tuple[str, ...]

    def __post_init__(self) -> None:
        _nonempty(self.source_name, "source_name")
        _timestamp(self.observed_at, "observed_at")
        _nonempty(self.source_payload_ref, "source_payload_ref")
        _checksum(self.source_payload_checksum)
        if not self.field_names:
            raise EvidenceError("field_names must be non-empty")
        cleaned = tuple(_nonempty(name, "field_name") for name in self.field_names)
        if len(cleaned) != len(set(cleaned)):
            raise EvidenceError("field_names must not contain duplicates")


@dataclass(frozen=True, slots=True)
class FeatureSnapshot:
    snapshot_id: str
    game_id: str
    feature_version: str
    generated_at: str
    source_data_cutoff_at: str
    kickoff_at: str
    features: Mapping[str, Any]
    sources: tuple[FeatureSource, ...]
    null_reasons: Mapping[str, str]
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field in ("snapshot_id", "game_id", "feature_version", "schema_version"):
            _nonempty(getattr(self, field), field)

        generated = _timestamp(self.generated_at, "generated_at")
        cutoff = _timestamp(self.source_data_cutoff_at, "source_data_cutoff_at")
        kickoff = _timestamp(self.kickoff_at, "kickoff_at")
        if cutoff > generated:
            raise EvidenceError("source_data_cutoff_at cannot exceed generated_at")
        if generated >= kickoff:
            raise EvidenceError("feature snapshot must be generated before kickoff")
        if not self.sources:
            raise EvidenceError("feature snapshot must contain at least one source")

        source_names: set[str] = set()
        for source in self.sources:
            observed = _timestamp(source.observed_at, "source.observed_at")
            if observed > cutoff:
                raise EvidenceError("feature source exceeds source_data_cutoff_at")
            identity = (
                source.source_name,
                source.source_payload_ref,
                source.source_payload_checksum,
            )
            encoded = json.dumps(identity, separators=(",", ":"))
            if encoded in source_names:
                raise EvidenceError("duplicate feature source")
            source_names.add(encoded)

        if not self.features:
            raise EvidenceError("features must be non-empty")

        for name, value in self.features.items():
            key = _nonempty(name, "feature_name")
            _feature_scalar(value, f"features.{key}")
            if value is None:
                reason = self.null_reasons.get(key)
                if not reason or not str(reason).strip():
                    raise EvidenceError(
                        f"null feature {key} requires an explicit null reason"
                    )
            elif key in self.null_reasons:
                raise EvidenceError(
                    f"non-null feature {key} must not have a null reason"
                )

        unknown_nulls = set(self.null_reasons) - set(self.features)
        if unknown_nulls:
            raise EvidenceError("null reasons reference unknown features")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["features"] = dict(self.features)
        result["null_reasons"] = dict(self.null_reasons)
        return result


def build_feature_snapshot(
    *,
    game_id: str,
    feature_version: str,
    generated_at: str,
    kickoff_at: str,
    features: Mapping[str, Any],
    sources: tuple[FeatureSource, ...],
    null_reasons: Mapping[str, str] | None = None,
    schema_version: str = "1.0",
) -> FeatureSnapshot:
    """Build a deterministic snapshot from immutable source evidence."""

    if not sources:
        raise EvidenceError("feature snapshot must contain at least one source")
    cutoff = max(
        (_timestamp(source.observed_at, "source.observed_at") for source in sources),
    )
    identity = {
        "game_id": game_id,
        "feature_version": feature_version,
        "generated_at": generated_at,
        "source_data_cutoff_at": cutoff.isoformat(),
        "kickoff_at": kickoff_at,
        "features": dict(features),
        "sources": [asdict(source) for source in sources],
        "null_reasons": dict(null_reasons or {}),
        "schema_version": schema_version,
    }
    canonical = json.dumps(
        identity,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    snapshot_id = str(uuid.uuid5(_FEATURE_NAMESPACE, canonical))
    return FeatureSnapshot(
        snapshot_id=snapshot_id,
        game_id=game_id,
        feature_version=feature_version,
        generated_at=generated_at,
        source_data_cutoff_at=cutoff.isoformat(),
        kickoff_at=kickoff_at,
        features=dict(features),
        sources=sources,
        null_reasons=dict(null_reasons or {}),
        schema_version=schema_version,
    )


def canonical_feature_snapshot_json(snapshot: FeatureSnapshot) -> str:
    return json.dumps(
        snapshot.to_dict(),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
