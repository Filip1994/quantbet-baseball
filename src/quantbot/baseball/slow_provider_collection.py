"""Low-frequency API-Sports primary-provider collection.

Dynamic game/odds/settlement work always runs first. This collector may consume
only the budget left over afterwards and never polls static/slow endpoints on
the 15-minute market cadence.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from .api import BaseballAPIBudgetExceeded, BaseballAPIError
from .provider_data import (
    canonical_reference_catalog,
    canonical_standings,
    canonical_team_statistics,
)


class SlowProviderClient(Protocol):
    request_count: int
    remaining_budget: int

    def standings_with_receipt(
        self,
        league_id: int,
        season: int,
    ) -> tuple[list[dict[str, Any]], Any]: ...

    def team_statistics_with_receipt(
        self,
        team_id: int,
        league_id: int,
        season: int,
    ) -> tuple[dict[str, Any], Any]: ...

    def bet_types_with_receipt(self) -> tuple[list[dict[str, Any]], Any]: ...

    def bookmakers_with_receipt(self) -> tuple[list[dict[str, Any]], Any]: ...


class SlowProviderRepository(Protocol):
    def latest_standings_observed_at(
        self,
        *,
        league_id: int,
        season: int,
    ) -> datetime | None: ...

    def latest_standing_team_ids(
        self,
        *,
        league_id: int,
        season: int,
    ) -> tuple[int, ...]: ...

    def latest_team_statistics_times(
        self,
        *,
        league_id: int,
        season: int,
    ) -> dict[int, datetime]: ...

    def latest_catalog_observed_at(self, catalog_type: str) -> datetime | None: ...

    def append_standings(self, records: Any) -> int: ...

    def append_team_statistics(self, record: Any) -> bool: ...

    def append_catalog(self, record: Any) -> bool: ...


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("provider-data repository timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _due(
    last_seen: datetime | None,
    now: datetime,
    cadence: timedelta,
) -> bool:
    seen = _as_utc(last_seen)
    return seen is None or now - seen >= cadence


def collect_slow_provider_data(
    client: SlowProviderClient,
    repository: SlowProviderRepository,
    *,
    now: datetime,
    max_requests: int,
    league_id: int = 1,
    season: int | None = None,
    standings_cadence: timedelta = timedelta(hours=24),
    team_statistics_cadence: timedelta = timedelta(hours=24),
    catalog_cadence: timedelta = timedelta(days=7),
) -> dict[str, int | str]:
    """Collect due slow data without exceeding leftover cycle budget."""

    if max_requests < 0:
        raise ValueError("max_requests cannot be negative")
    now = now.astimezone(UTC)
    season = season or now.year
    budget = min(max_requests, client.remaining_budget)

    summary: dict[str, int | str] = {
        "status": "collected",
        "request_cap": budget,
        "requests": 0,
        "standings_calls": 0,
        "standings_rows": 0,
        "standings_inserted": 0,
        "team_statistics_calls": 0,
        "team_statistics_inserted": 0,
        "team_statistics_due_uncollected": 0,
        "catalog_calls": 0,
        "catalogs_inserted": 0,
        "errors": 0,
    }
    if budget == 0:
        return summary

    requests_before = client.request_count
    team_ids: tuple[int, ...] = repository.latest_standing_team_ids(
        league_id=league_id,
        season=season,
    )

    standings_seen = repository.latest_standings_observed_at(
        league_id=league_id,
        season=season,
    )
    if (
        _due(standings_seen, now, standings_cadence)
        and client.request_count - requests_before < budget
    ):
        try:
            rows, receipt = client.standings_with_receipt(league_id, season)
            records = canonical_standings(
                rows,
                receipt,
                league_id=league_id,
                season=season,
            )
            summary["standings_calls"] = 1
            summary["standings_rows"] = len(records)
            summary["standings_inserted"] = repository.append_standings(records)
            if records:
                team_ids = tuple(dict.fromkeys(record.team_id for record in records))
        except BaseballAPIBudgetExceeded:
            pass
        except (BaseballAPIError, ValueError):
            summary["errors"] = int(summary["errors"]) + 1

    latest_team_stats = repository.latest_team_statistics_times(
        league_id=league_id,
        season=season,
    )
    due_team_ids = [
        team_id
        for team_id in team_ids
        if _due(latest_team_stats.get(team_id), now, team_statistics_cadence)
    ]

    for team_id in due_team_ids:
        if client.request_count - requests_before >= budget:
            break
        try:
            payload, receipt = client.team_statistics_with_receipt(
                team_id,
                league_id,
                season,
            )
            record = canonical_team_statistics(payload, receipt)
            summary["team_statistics_calls"] = int(summary["team_statistics_calls"]) + 1
            if repository.append_team_statistics(record):
                summary["team_statistics_inserted"] = (
                    int(summary["team_statistics_inserted"]) + 1
                )
        except BaseballAPIBudgetExceeded:
            break
        except (BaseballAPIError, ValueError):
            summary["errors"] = int(summary["errors"]) + 1

    completed_team_calls = int(summary["team_statistics_calls"])
    summary["team_statistics_due_uncollected"] = max(
        0,
        len(due_team_ids) - completed_team_calls,
    )

    catalogs = (
        ("BET_TYPES", client.bet_types_with_receipt),
        ("BOOKMAKERS", client.bookmakers_with_receipt),
    )
    for catalog_type, fetch in catalogs:
        if client.request_count - requests_before >= budget:
            break
        if not _due(
            repository.latest_catalog_observed_at(catalog_type),
            now,
            catalog_cadence,
        ):
            continue
        try:
            rows, receipt = fetch()
            record = canonical_reference_catalog(
                rows,
                receipt,
                catalog_type=catalog_type,
            )
            summary["catalog_calls"] = int(summary["catalog_calls"]) + 1
            if repository.append_catalog(record):
                summary["catalogs_inserted"] = int(summary["catalogs_inserted"]) + 1
        except BaseballAPIBudgetExceeded:
            break
        except (BaseballAPIError, ValueError):
            summary["errors"] = int(summary["errors"]) + 1

    summary["requests"] = client.request_count - requests_before
    return summary
