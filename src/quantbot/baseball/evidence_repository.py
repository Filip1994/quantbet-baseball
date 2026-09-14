"""Storage-neutral repository contract for canonical baseball evidence.

The repository boundary deliberately exposes append-only operations and
read-only retrieval. Concrete adapters (for example PostgreSQL on Railway)
must preserve the identity, idempotency, conflict, and ordering semantics
already defined by :mod:`evidence_store`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from .evidence import OddsObservation, PickEvent


@dataclass(frozen=True)
class RepositoryStats:
    observations: int
    pick_events: int


class EvidenceRepository(Protocol):
    """Minimal contract required by ingestion, replay, and evaluation code."""

    def append_observation(self, record: OddsObservation) -> bool:
        """Append one observation; return False for an exact duplicate."""
        ...

    def append_observations(self, records: Iterable[OddsObservation]) -> int:
        """Append observations atomically according to the adapter contract."""
        ...

    def append_pick_event(self, record: PickEvent) -> bool:
        """Append one immutable pick event; return False for an exact duplicate."""
        ...

    def get_observation(self, observation_id: str) -> OddsObservation | None:
        ...

    def get_pick_event(self, pick_id: str) -> PickEvent | None:
        ...

    def observations(self) -> tuple[OddsObservation, ...]:
        """Return observations in deterministic order."""
        ...

    def pick_events(self) -> tuple[PickEvent, ...]:
        """Return pick events in deterministic order."""
        ...

    def stats(self) -> RepositoryStats:
        ...
