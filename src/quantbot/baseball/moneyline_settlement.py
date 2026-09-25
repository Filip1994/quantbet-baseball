"""Priority authoritative-result refresh and paper settlement loop."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from .api import BaseballAPIBudgetExceeded, BaseballAPIError
from .fixture_evidence import canonical_fixture_observation
from .settlement_lifecycle import build_game_result_fact
from .settlement_repository import PostgreSQLMoneylineSettlementRepository


class SettlementClient(Protocol):
    request_count: int
    remaining_budget: int

    def game_with_receipt(self, game_id: int) -> tuple[list[dict[str, Any]], Any]: ...


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)


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


def settle_due_moneyline_picks(
    client: SettlementClient,
    repository: PostgreSQLMoneylineSettlementRepository,
    *,
    now: datetime,
    max_refreshes: int = 10,
) -> dict[str, int | str]:
    """Refresh closed picks and settle only from terminal provider result evidence."""

    current = _utc(now)
    if max_refreshes < 1:
        raise ValueError("max_refreshes must be positive")

    due = repository.due_pick_ids(as_of=current, limit=max_refreshes)
    game_calls = 0
    fixture_observations_inserted = 0
    result_facts_inserted = 0
    settlements = 0
    wins = 0
    losses = 0
    pushes = 0
    clv_available = 0
    clv_unavailable = 0
    nonterminal = 0
    errors = 0

    for pick_id in due:
        try:
            pick, prior_fixture = repository.refresh_context(
                pick_id,
                as_of=current,
            )
            provider_game_id = int(prior_fixture.provider_game_id)
            games, receipt = client.game_with_receipt(provider_game_id)
            game_calls += 1
            game_row = _provider_game_row(games, provider_game_id)
            if game_row is None:
                errors += 1
                continue

            fixture = canonical_fixture_observation(game_row, receipt)
            if fixture is None:
                errors += 1
                continue
            fixture_observations_inserted += repository.append_fixture_observations(
                (fixture,)
            )
            result = build_game_result_fact(game_row, fixture, receipt)
            if result is None:
                nonterminal += 1
                continue

            if repository.append_result(result):
                result_facts_inserted += 1
            settlement = repository.settle(
                pick.pick_id,
                result,
                settled_at=max(
                    current,
                    datetime.fromisoformat(result.observed_at).astimezone(UTC),
                ),
            )
            settlements += 1
            if settlement.outcome == "WIN":
                wins += 1
            elif settlement.outcome == "LOSS":
                losses += 1
            else:
                pushes += 1
            if settlement.clv_status == "AVAILABLE":
                clv_available += 1
            else:
                clv_unavailable += 1

        except BaseballAPIBudgetExceeded:
            break
        except (BaseballAPIError, LookupError, RuntimeError, TypeError, ValueError):
            errors += 1

    return {
        "status": "settled",
        "due_picks": len(due),
        "game_calls": game_calls,
        "fixture_observations_inserted": fixture_observations_inserted,
        "result_facts_inserted": result_facts_inserted,
        "settlements": settlements,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "clv_available": clv_available,
        "clv_unavailable": clv_unavailable,
        "nonterminal": nonterminal,
        "api_requests": client.request_count,
        "api_remaining": client.remaining_budget,
        "errors": errors,
    }
