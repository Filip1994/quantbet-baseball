"""Canonical, immutable evidence contracts for pre-game baseball markets.

This module is deliberately storage-agnostic. It validates the evidence boundary
before observations or pick events can be persisted or replayed.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class EvidenceError(ValueError):
    """Raised when an evidence record violates the canonical contract."""


class MarketFamily(str, Enum):
    MONEYLINE = "moneyline"
    TOTAL = "total"


class MarketStatus(str, Enum):
    OPEN = "open"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class Decision(str, Enum):
    BET = "BET"
    PASS = "PASS"


def _timestamp(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise EvidenceError(f"{field} must be a non-empty ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise EvidenceError(f"{field} is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{field} must be timezone-aware")
    return parsed


def _finite_number(value: Any, field: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise EvidenceError(f"{field} must be finite")
    if minimum is not None and number <= minimum:
        raise EvidenceError(f"{field} must be greater than {minimum}")
    return number


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{field} must be a non-empty string")
    return value


@dataclass(frozen=True)
class OddsObservation:
    observation_id: str
    game_id: str
    market_family: str
    line: float | None
    selection: str
    bookmaker: str
    decimal_odds: float
    raw_price: str
    observed_at: str
    retrieved_at: str
    source_payload_ref: str
    source_payload_checksum: str
    schema_version: str
    market_status: str
    kickoff_at: str

    def __post_init__(self) -> None:
        for name in (
            "observation_id",
            "game_id",
            "selection",
            "bookmaker",
            "raw_price",
            "source_payload_ref",
            "source_payload_checksum",
            "schema_version",
        ):
            _nonempty(getattr(self, name), name)
        if self.market_family not in {m.value for m in MarketFamily}:
            raise EvidenceError("market_family is unsupported")
        if self.market_status not in {s.value for s in MarketStatus}:
            raise EvidenceError("market_status is unsupported")
        if self.market_family == MarketFamily.TOTAL.value:
            _finite_number(self.line, "line")
        elif self.line is not None:
            raise EvidenceError("moneyline observations must not contain a line")
        _finite_number(self.decimal_odds, "decimal_odds", minimum=1.0)
        observed = _timestamp(self.observed_at, "observed_at")
        retrieved = _timestamp(self.retrieved_at, "retrieved_at")
        kickoff = _timestamp(self.kickoff_at, "kickoff_at")
        if retrieved < observed:
            raise EvidenceError("retrieved_at cannot precede observed_at")
        if observed >= kickoff:
            raise EvidenceError("pre-game observation cannot be at or after kickoff_at")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PickEvent:
    pick_id: str
    game_id: str
    market_family: str
    line: float | None
    selection: str
    decision: str
    decision_reason: str
    decision_at: str
    model_version: str
    feature_snapshot_ref: str
    market_snapshot_ref: str
    decision_decimal_odds: float | None
    model_probability: float | None
    fair_decimal_odds: float | None
    market_implied_probability: float | None
    edge: float | None
    expected_value_per_unit: float | None
    uncertainty_metric: float | None
    source_data_cutoff_at: str
    schema_version: str

    def __post_init__(self) -> None:
        for name in (
            "pick_id",
            "game_id",
            "selection",
            "decision_reason",
            "model_version",
            "feature_snapshot_ref",
            "market_snapshot_ref",
            "source_data_cutoff_at",
            "schema_version",
        ):
            _nonempty(getattr(self, name), name)
        if self.market_family not in {m.value for m in MarketFamily}:
            raise EvidenceError("market_family is unsupported")
        if self.market_family == MarketFamily.TOTAL.value:
            _finite_number(self.line, "line")
        elif self.line is not None:
            raise EvidenceError("moneyline pick events must not contain a line")
        if self.decision not in {d.value for d in Decision}:
            raise EvidenceError("decision must be BET or PASS")
        _timestamp(self.decision_at, "decision_at")
        _timestamp(self.source_data_cutoff_at, "source_data_cutoff_at")
        if self.decision == Decision.BET.value:
            for name in (
                "decision_decimal_odds",
                "model_probability",
                "fair_decimal_odds",
                "market_implied_probability",
                "edge",
                "expected_value_per_unit",
            ):
                _finite_number(getattr(self, name), name)
            _finite_number(
                self.decision_decimal_odds, "decision_decimal_odds", minimum=1.0
            )
            for name in ("model_probability", "market_implied_probability"):
                value = float(getattr(self, name))
                if not 0.0 <= value <= 1.0:
                    raise EvidenceError(f"{name} must be between 0 and 1")
        else:
            # PASS events are retained, but numerical metrics are explicitly unknown.
            for name in (
                "decision_decimal_odds",
                "model_probability",
                "fair_decimal_odds",
                "market_implied_probability",
                "edge",
                "expected_value_per_unit",
                "uncertainty_metric",
            ):
                if getattr(self, name) is not None:
                    raise EvidenceError(f"PASS event must leave {name} null")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def canonical_json(record: OddsObservation | PickEvent) -> str:
    """Return deterministic compact JSON for hashing and JSONL persistence."""
    return json.dumps(
        record.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )


def payload_checksum(payload: Mapping[str, Any]) -> str:
    """Hash a source payload using the same deterministic JSON representation."""
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
