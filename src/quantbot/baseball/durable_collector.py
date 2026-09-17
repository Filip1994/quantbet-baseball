"""Durable Railway collector: API -> bucket -> canonical PostgreSQL evidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
from typing import Any, Protocol

import psycopg

from .api import BaseballAPIBudgetExceeded, BaseballAPIClient, BaseballAPIError
from .collector import (
    _game_id,
    _game_time,
    _league_name,
    _team_names,
    compact_odds,
)
from .config import BaseballSettings
from .db import database_url_from_env
from .evidence import OddsObservation
from .ingestion import canonical_moneyline_observations
from .postgres_repository import PostgreSQLEvidenceRepository
from .raw_archive import archive_from_env
from .scheduler import build_scheduler_record, is_observation_due


_ADVISORY_LOCK_KEY = 726478920260918


class CollectorRepository(Protocol):
    def latest_observation_times(self) -> dict[str, datetime]: ...

    def append_observations(self, records: tuple[OddsObservation, ...]) -> int: ...


class CollectorClient(Protocol):
    request_count: int
    remaining_budget: int

    def games_by_date(self, date_iso: str) -> list[dict[str, Any]]: ...

    def odds_with_receipt(self, game_id: int) -> tuple[list[dict[str, Any]], Any]: ...


def _market_row_count(compact: dict[str, Any]) -> int:
    return sum(
        len(market.get("values") or [])
        for bookmaker in compact.get("bookmakers") or []
        for market in bookmaker.get("markets") or []
        if isinstance(market, dict)
    )


def collect_with_dependencies(
    client: CollectorClient,
    repository: CollectorRepository,
    *,
    now: datetime,
    max_odds_requests: int,
) -> dict[str, int | str]:
    """Collect one strict pregame cycle with injectable boundaries for tests."""

    now = now.astimezone(UTC)
    games: list[dict[str, Any]] = []
    seen_game_ids: set[int] = set()
    errors = 0

    for date_value in (now.date(), now.date() + timedelta(days=1)):
        try:
            date_games = client.games_by_date(date_value.isoformat())
        except BaseballAPIBudgetExceeded:
            break
        except BaseballAPIError:
            errors += 1
            continue

        for game in date_games:
            game_id = _game_id(game)
            if game_id is not None and game_id not in seen_game_ids:
                games.append(game)
                seen_game_ids.add(game_id)

    last_seen = repository.latest_observation_times()
    due: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    learning: list[tuple[float, dict[str, Any], dict[str, Any]]] = []

    for game in games:
        kickoff = _game_time(game)
        game_id = _game_id(game)
        if kickoff is None or game_id is None:
            continue

        minutes = (kickoff - now).total_seconds() / 60.0
        if not 0 < minutes <= 36 * 60:
            continue

        prior = last_seen.get(str(game_id))
        scheduler_record = build_scheduler_record(
            {"game_id": game_id, "kickoff": kickoff},
            now,
            prior,
        )
        item = (minutes, game, scheduler_record)
        learning.append(item)
        if is_observation_due(kickoff, now, prior):
            due.append(item)

    due.sort(key=lambda item: (item[0], item[2]["event_id"]))
    learning.sort(key=lambda item: (item[0], item[2]["event_id"]))

    selected: list[dict[str, Any]] = []
    selected_ids: set[int] = set()
    for source in (due, learning):
        for _, game, _ in source:
            game_id = _game_id(game)
            if (
                game_id is not None
                and game_id not in selected_ids
                and len(selected) < max_odds_requests
            ):
                selected.append(game)
                selected_ids.add(game_id)

    odds_calls = 0
    raw_market_rows = 0
    canonical_rows = 0
    inserted = 0

    for game in selected:
        game_id = _game_id(game)
        kickoff = _game_time(game)
        if game_id is None or kickoff is None or datetime.now(UTC) >= kickoff:
            continue

        try:
            odds, receipt = client.odds_with_receipt(game_id)
        except BaseballAPIBudgetExceeded:
            break
        except BaseballAPIError:
            errors += 1
            continue

        odds_calls += 1
        compact = compact_odds(odds)
        raw_market_rows += _market_row_count(compact)
        home, away = _team_names(game)
        snapshot = {
            "captured_at": receipt.captured_at,
            "game_id": game_id,
            "kickoff": kickoff.isoformat(),
            "league": _league_name(game) or "UNKNOWN",
            "home": home,
            "away": away,
            "odds": compact,
        }
        records = canonical_moneyline_observations(snapshot, receipt)
        canonical_rows += len(records)
        inserted += repository.append_observations(records)

    return {
        "status": "collected",
        "games_seen": len(games),
        "pregame_games": len(learning),
        "due_events": len(due),
        "games_selected": len(selected),
        "odds_calls": odds_calls,
        "raw_market_rows": raw_market_rows,
        "canonical_rows": canonical_rows,
        "observations_inserted": inserted,
        "api_requests": client.request_count,
        "api_remaining": client.remaining_budget,
        "errors": errors,
    }


def collect_durable_once(
    root: Path,
    *,
    now: datetime | None = None,
) -> dict[str, int | str]:
    """Run one production collection cycle with DB locking and remote archive."""

    settings = BaseballSettings.from_env(root)
    archive = archive_from_env(settings.raw_archive_dir, require_remote=True)
    client = BaseballAPIClient(settings, raw_archive=archive)
    max_odds_requests = int(os.getenv("BASEBALL_MAX_ODDS_REQUESTS", "76"))
    if max_odds_requests < 1:
        raise ValueError("BASEBALL_MAX_ODDS_REQUESTS must be positive")

    with psycopg.connect(database_url_from_env()) as connection:
        locked = connection.execute(
            "SELECT pg_try_advisory_lock(%s)",
            (_ADVISORY_LOCK_KEY,),
        ).fetchone()
        if locked is None or not bool(locked[0]):
            return {
                "status": "skipped_locked",
                "api_requests": 0,
                "api_remaining": settings.api_request_budget,
            }

        try:
            repository = PostgreSQLEvidenceRepository(connection)
            return collect_with_dependencies(
                client,
                repository,
                now=now or datetime.now(UTC),
                max_odds_requests=max_odds_requests,
            )
        finally:
            connection.execute(
                "SELECT pg_advisory_unlock(%s)",
                (_ADVISORY_LOCK_KEY,),
            )
