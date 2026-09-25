"""Registered-pick monitoring and immutable closing facts for Baseball moneyline."""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from .decision_lifecycle import RegisteredPick
from .evidence import EvidenceError, OddsObservation
from .fixture_evidence import FixtureObservation

_MONITORING_TRANSITION_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/pick-monitoring-transition/v1",
)
_CLOSING_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/pick-closing-finalization/v1",
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


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise EvidenceError(f"{field} must be a positive integer")
    return value


def _uuid(namespace: uuid.UUID, identity: str) -> str:
    return str(uuid.uuid5(namespace, identity))


@dataclass(frozen=True, slots=True)
class OddsLifecyclePolicy:
    monitoring_interval_seconds: int = 900
    current_max_age_seconds: int = 1800
    closing_max_age_seconds: int = 1200
    version: str = "BASEBALL_ODDS_LIFECYCLE_V1"

    def __post_init__(self) -> None:
        _positive_int(self.monitoring_interval_seconds, "monitoring_interval_seconds")
        _positive_int(self.current_max_age_seconds, "current_max_age_seconds")
        _positive_int(self.closing_max_age_seconds, "closing_max_age_seconds")
        if self.version != "BASEBALL_ODDS_LIFECYCLE_V1":
            raise EvidenceError("unsupported odds lifecycle policy version")


@dataclass(frozen=True, slots=True)
class MonitoringRecord:
    pick_id: str
    state: str
    policy: OddsLifecyclePolicy
    started_at: str
    next_refresh_at: str | None
    updated_at: str
    version: int

    def __post_init__(self) -> None:
        if not self.pick_id:
            raise EvidenceError("pick_id must be non-empty")
        if self.state not in {"MONITORING", "CLOSED_FOR_ODDS"}:
            raise EvidenceError("unsupported monitoring state")
        _timestamp(self.started_at, "started_at")
        _timestamp(self.updated_at, "updated_at")
        _positive_int(self.version, "version")
        if self.state == "MONITORING":
            if self.next_refresh_at is None:
                raise EvidenceError("MONITORING requires next_refresh_at")
            _timestamp(self.next_refresh_at, "next_refresh_at")
        elif self.next_refresh_at is not None:
            raise EvidenceError("CLOSED_FOR_ODDS cannot have next_refresh_at")


@dataclass(frozen=True, slots=True)
class OddsCheckpoint:
    observation_id: str
    game_id: str
    bookmaker: str
    selection: str
    decimal_odds: float
    observed_at: str
    kickoff_at: str
    freshness: str | None = None

    def __post_init__(self) -> None:
        if not self.observation_id or not self.game_id or not self.bookmaker:
            raise EvidenceError("checkpoint identity must be non-empty")
        if self.selection not in {"home", "away"}:
            raise EvidenceError("checkpoint selection is unsupported")
        if not math.isfinite(self.decimal_odds) or self.decimal_odds <= 1.0:
            raise EvidenceError("checkpoint odds must be valid decimal odds")
        _timestamp(self.observed_at, "observed_at")
        _timestamp(self.kickoff_at, "kickoff_at")
        if self.freshness not in {None, "FRESH", "STALE"}:
            raise EvidenceError("checkpoint freshness is unsupported")

    @classmethod
    def from_observation(
        cls,
        observation: OddsObservation,
        *,
        freshness: str | None = None,
    ) -> OddsCheckpoint:
        return cls(
            observation_id=observation.observation_id,
            game_id=observation.game_id,
            bookmaker=observation.bookmaker,
            selection=observation.selection,
            decimal_odds=observation.decimal_odds,
            observed_at=observation.observed_at,
            kickoff_at=observation.kickoff_at,
            freshness=freshness,
        )


@dataclass(frozen=True, slots=True)
class ClosingFinalization:
    finalization_id: str
    pick_id: str
    game_id: str
    fixture_observation_id: str
    cutoff_at: str
    bookmaker: str
    selection: str
    finalized_at: str
    outcome: str
    candidate_home_observation_id: str | None
    candidate_away_observation_id: str | None
    closing_observation_id: str | None
    lifecycle_policy_version: str
    closing_max_age_seconds: int
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field in (
            "finalization_id",
            "pick_id",
            "game_id",
            "fixture_observation_id",
            "bookmaker",
            "lifecycle_policy_version",
            "schema_version",
        ):
            if not str(getattr(self, field) or "").strip():
                raise EvidenceError(f"{field} must be non-empty")
        if self.selection not in {"home", "away"}:
            raise EvidenceError("closing selection is unsupported")
        if self.outcome not in {"CAPTURED", "STALE_QUOTE", "NO_VALID_QUOTE"}:
            raise EvidenceError("closing outcome is unsupported")
        cutoff = _timestamp(self.cutoff_at, "cutoff_at")
        finalized = _timestamp(self.finalized_at, "finalized_at")
        if finalized < cutoff:
            raise EvidenceError("closing cannot finalize before cutoff")
        _positive_int(self.closing_max_age_seconds, "closing_max_age_seconds")
        pair = (
            self.candidate_home_observation_id,
            self.candidate_away_observation_id,
        )
        pair_complete = all(value is not None for value in pair)
        pair_empty = all(value is None for value in pair)
        if not pair_complete and not pair_empty:
            raise EvidenceError("closing candidate pair must be complete")
        if self.outcome == "CAPTURED":
            if not pair_complete or self.closing_observation_id is None:
                raise EvidenceError(
                    "CAPTURED closing requires quote pair and selected close"
                )
        elif self.outcome == "STALE_QUOTE":
            if not pair_complete or self.closing_observation_id is not None:
                raise EvidenceError("STALE_QUOTE cannot expose closing observation")
        elif not pair_empty or self.closing_observation_id is not None:
            raise EvidenceError("NO_VALID_QUOTE cannot contain candidate observations")


def canonical_closing_json(record: ClosingFinalization) -> str:
    return json.dumps(
        asdict(record),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def monitoring_transition_id(pick_id: str, transition_type: str) -> str:
    if transition_type not in {"MONITORING_STARTED", "ODDS_CLOSED"}:
        raise EvidenceError("unsupported monitoring transition")
    return _uuid(
        _MONITORING_TRANSITION_NAMESPACE,
        f"{pick_id}:{transition_type}",
    )


def _validate_pair(
    pick: RegisteredPick,
    home: OddsObservation,
    away: OddsObservation,
    *,
    cutoff_at: datetime,
) -> None:
    if home.market_family != "moneyline" or away.market_family != "moneyline":
        raise EvidenceError("closing pair must be moneyline")
    if home.selection != "home" or away.selection != "away":
        raise EvidenceError("closing pair must contain home and away")
    if home.game_id != pick.game_id or away.game_id != pick.game_id:
        raise EvidenceError("closing pair game mismatch")
    if home.bookmaker != pick.bookmaker or away.bookmaker != pick.bookmaker:
        raise EvidenceError("closing pair bookmaker mismatch")
    if home.observed_at != away.observed_at:
        raise EvidenceError("closing pair must share observation time")
    observed = _timestamp(home.observed_at, "observed_at")
    if observed >= cutoff_at:
        raise EvidenceError("closing candidate must be strictly pre-kickoff")


def build_closing_finalization(
    pick: RegisteredPick,
    fixture: FixtureObservation,
    *,
    finalized_at: str,
    policy: OddsLifecyclePolicy,
    pair: tuple[OddsObservation, OddsObservation] | None,
) -> ClosingFinalization:
    if fixture.game_id != pick.game_id:
        raise EvidenceError("fixture and pick game mismatch")
    cutoff = _timestamp(fixture.kickoff_at, "kickoff_at")
    finalized = _timestamp(finalized_at, "finalized_at")
    if finalized < cutoff:
        raise EvidenceError("authoritative kickoff cutoff has not passed")

    outcome = "NO_VALID_QUOTE"
    home_id = None
    away_id = None
    closing_id = None

    if pair is not None:
        home, away = pair
        _validate_pair(pick, home, away, cutoff_at=cutoff)
        home_id = home.observation_id
        away_id = away.observation_id
        observed = _timestamp(home.observed_at, "observed_at")
        age_seconds = (cutoff - observed).total_seconds()
        if age_seconds <= policy.closing_max_age_seconds:
            outcome = "CAPTURED"
            selected = home if pick.selection == "home" else away
            closing_id = selected.observation_id
        else:
            outcome = "STALE_QUOTE"

    return ClosingFinalization(
        finalization_id=_uuid(_CLOSING_NAMESPACE, pick.pick_id),
        pick_id=pick.pick_id,
        game_id=pick.game_id,
        fixture_observation_id=fixture.fixture_observation_id,
        cutoff_at=fixture.kickoff_at,
        bookmaker=pick.bookmaker,
        selection=pick.selection,
        finalized_at=finalized_at,
        outcome=outcome,
        candidate_home_observation_id=home_id,
        candidate_away_observation_id=away_id,
        closing_observation_id=closing_id,
        lifecycle_policy_version=policy.version,
        closing_max_age_seconds=policy.closing_max_age_seconds,
    )


@dataclass(frozen=True, slots=True)
class PickOddsLifecycle:
    pick_id: str
    state: str
    opening: OddsCheckpoint | None
    entry: OddsCheckpoint
    current: OddsCheckpoint | None
    closing: OddsCheckpoint | None
    closing_outcome: str | None
    history: tuple[OddsCheckpoint, ...]
    markers: dict[str, tuple[str, ...]]
