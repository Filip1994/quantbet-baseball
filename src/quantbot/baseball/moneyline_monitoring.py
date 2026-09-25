"""Priority refresh loop for registered Baseball moneyline paper picks."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from .api import BaseballAPIBudgetExceeded, BaseballAPIError
from .collector import compact_odds
from .fixture_evidence import canonical_fixture_observation
from .ingestion import canonical_moneyline_observations
from .monitoring_lifecycle import OddsLifecyclePolicy
from .monitoring_repository import PostgreSQLMoneylineMonitoringRepository


class MonitoringClient(Protocol):
    request_count: int
    remaining_budget: int

    def game_with_receipt(self, game_id: int) -> tuple[list[dict[str, Any]], Any]: ...

    def odds_with_receipt(self, game_id: int) -> tuple[list[dict[str, Any]], Any]: ...


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)


def _pregame_status(value: str) -> bool:
    normalized = " ".join(value.strip().casefold().replace("_", " ").split())
    return normalized in {"ns", "not started", "scheduled", "tbd"}


def _provider_game_row(
    rows: list[dict[str, Any]],
    provider_game_id: int,
) -> dict[str, Any] | None:
    for row in rows:
        raw = row.get("id")
        if raw is None and isinstance(row.get("game"), dict):
            raw = row["game"].get("id")
        try:
            if int(raw) == provider_game_id:
                return row
        except (TypeError, ValueError):
            continue
    return None


def _has_exact_pair(records, bookmaker: str) -> bool:
    sides = {
        record.selection
        for record in records
        if record.bookmaker == bookmaker and record.selection in {"home", "away"}
    }
    return sides == {"home", "away"}


def monitor_due_moneyline_picks(
    client: MonitoringClient,
    repository: PostgreSQLMoneylineMonitoringRepository,
    *,
    now: datetime,
    policy: OddsLifecyclePolicy,
    max_refreshes: int = 10,
) -> dict[str, int | str]:
    """Refresh active picks before broad collection consumes the odds-call budget."""

    current = _utc(now)
    if max_refreshes < 1:
        raise ValueError("max_refreshes must be positive")

    started = 0
    errors = 0
    for pick_id in repository.unstarted_pick_ids(limit=max_refreshes):
        try:
            repository.start_monitoring(
                pick_id,
                started_at=current,
                policy=policy,
            )
            started += 1
        except (LookupError, RuntimeError, ValueError):
            errors += 1

    due = repository.due_pick_ids(as_of=current, limit=max_refreshes)
    fixture_calls = 0
    odds_calls = 0
    observations_inserted = 0
    exact_pair_refreshes = 0
    finalizations = 0
    captured = 0
    stale = 0
    no_valid = 0

    for pick_id in due:
        try:
            pick, prior_fixture = repository.refresh_context(
                pick_id,
                as_of=current,
            )
            provider_game_id = int(prior_fixture.provider_game_id)

            games, game_receipt = client.game_with_receipt(provider_game_id)
            fixture_calls += 1
            game_row = _provider_game_row(games, provider_game_id)
            if game_row is None:
                errors += 1
                continue
            fixture_record = canonical_fixture_observation(game_row, game_receipt)
            if fixture_record is None:
                errors += 1
                continue
            repository.append_fixture_observations((fixture_record,))
            _, fixture = repository.refresh_context(pick_id, as_of=current)

            cutoff = datetime.fromisoformat(fixture.kickoff_at).astimezone(UTC)
            if current >= cutoff:
                finalization = repository.finalize_closing(
                    pick_id,
                    finalized_at=current,
                )
                finalizations += 1
                if finalization.outcome == "CAPTURED":
                    captured += 1
                elif finalization.outcome == "STALE_QUOTE":
                    stale += 1
                else:
                    no_valid += 1
                continue

            if not _pregame_status(fixture.provider_status):
                repository.advance_refresh(pick_id, refreshed_at=current)
                continue

            odds, odds_receipt = client.odds_with_receipt(provider_game_id)
            odds_calls += 1
            compact = compact_odds(odds)
            snapshot = {
                "captured_at": odds_receipt.captured_at,
                "game_id": provider_game_id,
                "kickoff": fixture.kickoff_at,
                "league": fixture.league,
                "home": fixture.home_team_name,
                "away": fixture.away_team_name,
                "odds": compact,
            }
            records = canonical_moneyline_observations(snapshot, odds_receipt)
            observations_inserted += repository.append_observations(records)
            if _has_exact_pair(records, pick.bookmaker):
                exact_pair_refreshes += 1
            repository.advance_refresh(pick_id, refreshed_at=current)

        except BaseballAPIBudgetExceeded:
            break
        except (BaseballAPIError, LookupError, RuntimeError, TypeError, ValueError):
            errors += 1

    return {
        "status": "monitored",
        "monitoring_started": started,
        "due_picks": len(due),
        "fixture_calls": fixture_calls,
        "odds_calls": odds_calls,
        "observations_inserted": observations_inserted,
        "exact_pair_refreshes": exact_pair_refreshes,
        "finalizations": finalizations,
        "closing_captured": captured,
        "closing_stale": stale,
        "closing_no_valid_quote": no_valid,
        "api_requests": client.request_count,
        "api_remaining": client.remaining_budget,
        "errors": errors,
    }
