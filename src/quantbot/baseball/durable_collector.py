"""Durable Railway collector: API -> bucket -> canonical PostgreSQL evidence."""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
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
from .fixture_evidence import FixtureObservation, canonical_fixture_observation
from .ingestion import canonical_moneyline_observations
from .postgres_repository import PostgreSQLEvidenceRepository
from .raw_archive import archive_from_env
from .runtime_evidence import CollectionCycle
from .scheduler import build_scheduler_record, is_observation_due

_ADVISORY_LOCK_KEY = 726478920260918


class CollectorRepository(Protocol):
    def latest_observation_times(self) -> dict[str, datetime]: ...

    def append_observations(self, records: tuple[OddsObservation, ...]) -> int: ...

    def append_fixture_observations(
        self,
        records: tuple[FixtureObservation, ...],
    ) -> int: ...


class CollectorClient(Protocol):
    request_count: int
    remaining_budget: int

    def games_by_date_with_receipt(
        self,
        date_iso: str,
    ) -> tuple[list[dict[str, Any]], Any]: ...

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
    clock: Callable[[], datetime] | None = None,
) -> dict[str, int | str]:
    """Collect one strict pregame cycle with injectable boundaries for tests."""

    now = now.astimezone(UTC)
    current_time = clock or (lambda: datetime.now(UTC))
    games: list[dict[str, Any]] = []
    seen_game_ids: set[int] = set()
    errors = 0
    fixture_observations = 0
    fixtures_inserted = 0

    for date_value in (now.date(), now.date() + timedelta(days=1)):
        try:
            date_games, schedule_receipt = client.games_by_date_with_receipt(
                date_value.isoformat()
            )
        except BaseballAPIBudgetExceeded:
            break
        except BaseballAPIError:
            errors += 1
            continue

        fixture_records = tuple(
            record
            for game in date_games
            if (record := canonical_fixture_observation(game, schedule_receipt))
            is not None
        )
        fixture_observations += len(fixture_records)
        fixtures_inserted += repository.append_fixture_observations(fixture_records)

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
        if (
            game_id is None
            or kickoff is None
            or current_time().astimezone(UTC) >= kickoff
        ):
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
        "fixture_observations": fixture_observations,
        "fixture_observations_inserted": fixtures_inserted,
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

    cycle_started_at = datetime.now(UTC)
    cycle_now = now or cycle_started_at

    with psycopg.connect(database_url_from_env()) as connection:
        repository = PostgreSQLEvidenceRepository(connection)
        cycle_id = str(uuid.uuid4())
        locked = connection.execute(
            "SELECT pg_try_advisory_lock(%s)",
            (_ADVISORY_LOCK_KEY,),
        ).fetchone()
        if locked is None or not bool(locked[0]):
            summary = {
                "status": "skipped_locked",
                "api_requests": 0,
                "api_remaining": settings.api_request_budget,
            }
            repository.append_collection_cycle(
                CollectionCycle.from_summary(
                    cycle_id=cycle_id,
                    started_at=cycle_started_at,
                    finished_at=datetime.now(UTC),
                    summary=summary,
                )
            )
            return summary

        try:
            summary = collect_with_dependencies(
                client,
                repository,
                now=cycle_now,
                max_odds_requests=max_odds_requests,
            )
            repository.append_collection_cycle(
                CollectionCycle.from_summary(
                    cycle_id=cycle_id,
                    started_at=cycle_started_at,
                    finished_at=datetime.now(UTC),
                    summary=summary,
                )
            )
            return summary
        finally:
            connection.execute(
                "SELECT pg_advisory_unlock(%s)",
                (_ADVISORY_LOCK_KEY,),
            )
