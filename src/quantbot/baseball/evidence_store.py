"""Append-only, deterministic in-memory evidence store.

This is the persistence boundary for the first vertical slice. It deliberately
has no database dependency: the contract can be tested and later backed by
SQLite/PostgreSQL without changing identity or conflict semantics.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .evidence import EvidenceError, OddsObservation, PickEvent, canonical_json


@dataclass(frozen=True)
class StoreStats:
    observations: int
    pick_events: int


class EvidenceStore:
    """Append-only store with idempotent exact duplicates and fail-closed conflicts."""

    def __init__(self) -> None:
        self._observations: dict[str, OddsObservation] = {}
        self._pick_events: dict[str, PickEvent] = {}

    def append_observation(self, record: OddsObservation) -> bool:
        prior = self._observations.get(record.observation_id)
        if prior is not None:
            if canonical_json(prior) != canonical_json(record):
                raise EvidenceError("conflicting observation_id already exists")
            return False
        self._observations[record.observation_id] = record
        return True

    def append_pick_event(self, record: PickEvent) -> bool:
        prior = self._pick_events.get(record.pick_id)
        if prior is not None:
            if canonical_json(prior) != canonical_json(record):
                raise EvidenceError("conflicting pick_id already exists")
            return False
        self._pick_events[record.pick_id] = record
        return True

    def append_observations(self, records: Iterable[OddsObservation]) -> int:
        return sum(self.append_observation(record) for record in records)

    def get_observation(self, observation_id: str) -> OddsObservation | None:
        return self._observations.get(observation_id)

    def get_pick_event(self, pick_id: str) -> PickEvent | None:
        return self._pick_events.get(pick_id)

    def observations(self) -> tuple[OddsObservation, ...]:
        return tuple(sorted(self._observations.values(), key=lambda r: (r.observed_at, r.observation_id)))

    def pick_events(self) -> tuple[PickEvent, ...]:
        return tuple(sorted(self._pick_events.values(), key=lambda r: (r.decision_at, r.pick_id)))

    def stats(self) -> StoreStats:
        return StoreStats(len(self._observations), len(self._pick_events))
