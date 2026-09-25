"""Immutable collection-cycle telemetry for the Baseball runtime."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from .evidence import EvidenceError

_ALLOWED_STATUSES = {"collected", "skipped_locked"}


def _timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{field} must be timezone-aware")
    return parsed


def _nonnegative(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvidenceError(f"{field} must be a non-negative integer")
    return value


@dataclass(frozen=True, slots=True)
class CollectionCycle:
    cycle_id: str
    started_at: str
    finished_at: str
    status: str
    games_seen: int
    fixture_observations_inserted: int
    pregame_games: int
    due_events: int
    games_selected: int
    odds_calls: int
    raw_market_rows: int
    canonical_rows: int
    observations_inserted: int
    api_requests: int
    api_remaining: int
    errors: int
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if not self.cycle_id.strip():
            raise EvidenceError("cycle_id must be non-empty")
        started = _timestamp(self.started_at, "started_at")
        finished = _timestamp(self.finished_at, "finished_at")
        if finished < started:
            raise EvidenceError("finished_at cannot precede started_at")
        if self.status not in _ALLOWED_STATUSES:
            raise EvidenceError("collection cycle status is unsupported")
        for field in (
            "games_seen",
            "fixture_observations_inserted",
            "pregame_games",
            "due_events",
            "games_selected",
            "odds_calls",
            "raw_market_rows",
            "canonical_rows",
            "observations_inserted",
            "api_requests",
            "api_remaining",
            "errors",
        ):
            _nonnegative(getattr(self, field), field)
        if not self.schema_version.strip():
            raise EvidenceError("schema_version must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_summary(
        cls,
        *,
        cycle_id: str,
        started_at: datetime,
        finished_at: datetime,
        summary: dict[str, int | str],
    ) -> "CollectionCycle":
        return cls(
            cycle_id=cycle_id,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            status=str(summary["status"]),
            games_seen=int(summary.get("games_seen", 0)),
            fixture_observations_inserted=int(
                summary.get("fixture_observations_inserted", 0)
            ),
            pregame_games=int(summary.get("pregame_games", 0)),
            due_events=int(summary.get("due_events", 0)),
            games_selected=int(summary.get("games_selected", 0)),
            odds_calls=int(summary.get("odds_calls", 0)),
            raw_market_rows=int(summary.get("raw_market_rows", 0)),
            canonical_rows=int(summary.get("canonical_rows", 0)),
            observations_inserted=int(summary.get("observations_inserted", 0)),
            api_requests=int(summary.get("api_requests", 0)),
            api_remaining=int(summary.get("api_remaining", 0)),
            errors=int(summary.get("errors", 0)),
        )


def canonical_collection_cycle_json(record: CollectionCycle) -> str:
    return json.dumps(
        record.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
