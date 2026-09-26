"""Low-frequency API-Sports league-season game-history collection.

This consumes only leftover slow-source capacity. One fresh /games league-season
envelope is enough to refresh schedule/result history; all rest/density/extra
features are then derived locally.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from .api import BaseballAPIBudgetExceeded, BaseballAPIError
from .game_history import canonical_game_history


class GameHistoryClient(Protocol):
    request_count: int
    remaining_budget: int

    def games_by_league_season_with_receipt(
        self,
        league_id: int,
        season: int,
    ) -> tuple[list[dict[str, Any]], Any]: ...


class GameHistoryRepository(Protocol):
    def latest_observed_at(
        self,
        *,
        league_id: int,
        season: int,
    ) -> datetime | None: ...

    def append_snapshots(self, records: Any) -> int: ...


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("game-history repository timestamp must be timezone-aware")
    return value.astimezone(UTC)


def collect_game_history(
    client: GameHistoryClient,
    repository: GameHistoryRepository,
    *,
    now: datetime,
    max_requests: int,
    league_id: int = 1,
    season: int | None = None,
    cadence: timedelta = timedelta(hours=24),
) -> dict[str, int | str]:
    if max_requests < 0:
        raise ValueError("max_requests cannot be negative")

    now = now.astimezone(UTC)
    season = season or now.year
    request_cap = min(max_requests, client.remaining_budget)
    summary: dict[str, int | str] = {
        "status": "collected",
        "request_cap": request_cap,
        "requests": 0,
        "calls": 0,
        "rows": 0,
        "inserted": 0,
        "errors": 0,
    }
    if request_cap == 0:
        return summary

    latest = _as_utc(
        repository.latest_observed_at(
            league_id=league_id,
            season=season,
        )
    )
    if latest is not None and now - latest < cadence:
        return summary

    before = client.request_count
    try:
        rows, receipt = client.games_by_league_season_with_receipt(
            league_id,
            season,
        )
        records = canonical_game_history(
            rows,
            receipt,
            league_id=league_id,
            season=season,
        )
        summary["calls"] = 1
        summary["rows"] = len(records)
        summary["inserted"] = repository.append_snapshots(records)
    except BaseballAPIBudgetExceeded:
        pass
    except (BaseballAPIError, ValueError):
        summary["errors"] = 1

    summary["requests"] = client.request_count - before
    return summary
