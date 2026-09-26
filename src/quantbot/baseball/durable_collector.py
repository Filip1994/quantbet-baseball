"""Durable Railway collector: API -> bucket -> canonical PostgreSQL evidence."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import psycopg

from .api import BaseballAPIBudgetExceeded, BaseballAPIClient, BaseballAPIError
from .collector import (
    _bookmaker_records,
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
from .game_history_collection import collect_game_history
from .game_history_repository import PostgreSQLGameHistoryRepository
from .ingestion import canonical_moneyline_observations
from .moneyline_monitoring import monitor_due_moneyline_picks
from .moneyline_settlement import settle_due_moneyline_picks
from .monitoring_lifecycle import OddsLifecyclePolicy
from .monitoring_repository import PostgreSQLMoneylineMonitoringRepository
from .mlb_identity_bootstrap import collect_mlb_identity_bootstrap
from .mlb_identity_repository import PostgreSQLMLBIdentityRepository
from .official_mlb import OfficialMLBStatsClient
from .odds_poll_evidence import OddsPollAttempt, build_odds_poll_attempt
from .postgres_repository import PostgreSQLEvidenceRepository
from .provider_data_repository import PostgreSQLProviderDataRepository
from .raw_archive import archive_from_env
from .runtime_evidence import CollectionCycle
from .scheduler import build_scheduler_record, is_observation_due
from .settlement_repository import PostgreSQLMoneylineSettlementRepository
from .slow_provider_collection import collect_slow_provider_data

_ADVISORY_LOCK_KEY = 726478920260918


class CollectorRepository(Protocol):
    def latest_odds_poll_times(self) -> dict[str, datetime]: ...

    def append_observations(self, records: tuple[OddsObservation, ...]) -> int: ...

    def append_odds_poll_attempt(self, record: OddsPollAttempt) -> bool: ...

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


def remaining_broad_odds_capacity(
    *,
    cycle_request_cap: int,
    requests_used: int,
    max_odds_requests: int,
    schedule_request_reserve: int = 2,
) -> int:
    if cycle_request_cap < 1:
        raise ValueError("cycle_request_cap must be positive")
    if requests_used < 0 or max_odds_requests < 0 or schedule_request_reserve < 0:
        raise ValueError("request counts cannot be negative")
    return min(
        max_odds_requests,
        max(0, cycle_request_cap - requests_used - schedule_request_reserve),
    )


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
    schema_probe: bool = False,
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

    last_seen = repository.latest_odds_poll_times()
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

    # Scheduled broad odds polling must honor the adaptive scheduler.  The
    # previous due+learning fallback refilled spare capacity with explicitly
    # non-due games, effectively polling every eligible pregame game on every
    # 15-minute cron while the event count remained below the request cap.
    selected: list[dict[str, Any]] = []
    selected_ids: set[int] = set()
    for _, game, _ in due:
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
    poll_attempts_inserted = 0
    schema_market_names: set[str] = set()
    schema_candidate_values: dict[str, set[str]] = {}
    schema_odds_payload_rows = 0
    schema_empty_odds_calls = 0
    schema_nonempty_odds_calls = 0
    schema_bookmaker_records = 0
    schema_top_level_keys: set[str] = set()
    schema_response_shapes: set[str] = set()

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
        if schema_probe:
            schema_odds_payload_rows += len(odds)
            if odds:
                schema_nonempty_odds_calls += 1
            else:
                schema_empty_odds_calls += 1
            for item in odds:
                if not isinstance(item, dict):
                    continue
                keys = tuple(sorted(str(key) for key in item))
                schema_top_level_keys.update(keys)
                schema_response_shapes.add(",".join(keys))

            bookmaker_records = _bookmaker_records(odds)
            schema_bookmaker_records += len(bookmaker_records)
            for bookmaker in bookmaker_records:
                for market in bookmaker.get("markets") or []:
                    if not isinstance(market, dict):
                        continue
                    market_name = str(market.get("name") or "").strip()
                    if not market_name:
                        continue
                    schema_market_names.add(market_name)
                    normalized = " ".join(
                        market_name.casefold()
                        .replace("_", " ")
                        .replace("-", " ")
                        .split()
                    )
                    if any(
                        token in normalized
                        for token in (
                            "moneyline",
                            "money line",
                            "winner",
                            "result",
                            "home away",
                            "home/away",
                        )
                    ):
                        labels = schema_candidate_values.setdefault(market_name, set())
                        for value in market.get("values") or []:
                            if not isinstance(value, dict):
                                continue
                            label = str(value.get("value") or "").strip()
                            if label:
                                labels.add(label)

        compact = compact_odds(odds)
        raw_rows = _market_row_count(compact)
        raw_market_rows += raw_rows
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
        attempt = build_odds_poll_attempt(
            game_id=game_id,
            kickoff_at=kickoff,
            receipt=receipt,
            response_rows=len(odds),
            raw_market_rows=raw_rows,
            canonical_rows=len(records),
        )
        if repository.append_odds_poll_attempt(attempt):
            poll_attempts_inserted += 1

    result: dict[str, int | str] = {
        "status": "collected",
        "games_seen": len(games),
        "fixture_observations": fixture_observations,
        "fixture_observations_inserted": fixtures_inserted,
        "pregame_games": len(learning),
        "due_events": len(due),
        "not_due_events": max(0, len(learning) - len(due)),
        "games_selected": len(selected),
        "due_events_unselected": max(0, len(due) - len(selected)),
        "odds_calls": odds_calls,
        "raw_market_rows": raw_market_rows,
        "canonical_rows": canonical_rows,
        "observations_inserted": inserted,
        "poll_attempts_inserted": poll_attempts_inserted,
        "api_requests": client.request_count,
        "api_remaining": client.remaining_budget,
        "errors": errors,
    }
    if schema_probe:
        result["schema_odds_payload_rows"] = schema_odds_payload_rows
        result["schema_empty_odds_calls"] = schema_empty_odds_calls
        result["schema_nonempty_odds_calls"] = schema_nonempty_odds_calls
        result["schema_bookmaker_records"] = schema_bookmaker_records
        result["schema_top_level_keys_json"] = json.dumps(
            sorted(schema_top_level_keys)[:100],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        result["schema_response_shapes_json"] = json.dumps(
            sorted(schema_response_shapes)[:50],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        result["schema_market_names_json"] = json.dumps(
            sorted(schema_market_names)[:100],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        result["schema_candidate_values_json"] = json.dumps(
            {
                name: sorted(values)[:20]
                for name, values in sorted(schema_candidate_values.items())[:50]
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
    return result


def collect_durable_once(
    root: Path,
    *,
    now: datetime | None = None,
    execution_mode: str = "SCHEDULED",
    max_api_requests_per_cycle: int | None = None,
    max_odds_requests_override: int | None = None,
    max_monitoring_refreshes_override: int | None = None,
    max_settlement_refreshes_override: int | None = None,
) -> dict[str, int | str]:
    """Run one production collection cycle with DB locking and remote archive."""

    settings = BaseballSettings.from_env(root)
    if execution_mode not in {"SCHEDULED", "CANARY"}:
        raise ValueError("execution_mode must be SCHEDULED or CANARY")

    cycle_request_cap = (
        max_api_requests_per_cycle
        if max_api_requests_per_cycle is not None
        else int(os.getenv("BASEBALL_MAX_API_REQUESTS_PER_CYCLE", "75"))
    )
    if cycle_request_cap < 1:
        raise ValueError("BASEBALL_MAX_API_REQUESTS_PER_CYCLE must be positive")
    effective_request_cap = min(cycle_request_cap, settings.api_request_budget)

    archive = archive_from_env(settings.raw_archive_dir, require_remote=True)
    client = BaseballAPIClient(
        replace(settings, api_request_budget=effective_request_cap),
        raw_archive=archive,
    )
    max_odds_requests = (
        max_odds_requests_override
        if max_odds_requests_override is not None
        else int(os.getenv("BASEBALL_MAX_ODDS_REQUESTS", "76"))
    )
    max_monitoring_refreshes = (
        max_monitoring_refreshes_override
        if max_monitoring_refreshes_override is not None
        else int(os.getenv("BASEBALL_MAX_MONITORING_REFRESHES", "10"))
    )
    max_settlement_refreshes = (
        max_settlement_refreshes_override
        if max_settlement_refreshes_override is not None
        else int(os.getenv("BASEBALL_MAX_SETTLEMENT_REFRESHES", "10"))
    )
    if max_odds_requests < 1:
        raise ValueError("BASEBALL_MAX_ODDS_REQUESTS must be positive")
    if max_monitoring_refreshes < 1:
        raise ValueError("BASEBALL_MAX_MONITORING_REFRESHES must be positive")
    if max_settlement_refreshes < 1:
        raise ValueError("BASEBALL_MAX_SETTLEMENT_REFRESHES must be positive")

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
                "cycle_id": cycle_id,
                "execution_mode": execution_mode,
                "cycle_request_cap": effective_request_cap,
                "api_requests": 0,
                "api_remaining": effective_request_cap,
            }
            repository.append_collection_cycle(
                CollectionCycle.from_summary(
                    cycle_id=cycle_id,
                    started_at=cycle_started_at,
                    finished_at=datetime.now(UTC),
                    summary=summary,
                    execution_mode=execution_mode,
                )
            )
            return summary

        try:
            settlement_repository = PostgreSQLMoneylineSettlementRepository(connection)
            settlement = settle_due_moneyline_picks(
                client,
                settlement_repository,
                now=cycle_now,
                max_refreshes=max_settlement_refreshes,
            )
            monitoring_repository = PostgreSQLMoneylineMonitoringRepository(connection)
            monitoring = monitor_due_moneyline_picks(
                client,
                monitoring_repository,
                now=cycle_now,
                policy=OddsLifecyclePolicy(),
                max_refreshes=max_monitoring_refreshes,
            )
            remaining_odds_requests = remaining_broad_odds_capacity(
                cycle_request_cap=effective_request_cap,
                requests_used=client.request_count,
                max_odds_requests=max_odds_requests,
            )
            summary = collect_with_dependencies(
                client,
                repository,
                now=cycle_now,
                max_odds_requests=remaining_odds_requests,
                schema_probe=execution_mode == "CANARY",
            )

            slow_provider_enabled = os.getenv(
                "BASEBALL_ENABLE_SLOW_PROVIDER_COLLECTION", "false"
            ).strip().lower() in {"1", "true", "yes", "on"}
            max_slow_provider_requests = int(
                os.getenv("BASEBALL_MAX_SLOW_PROVIDER_REQUESTS", "8")
            )
            if max_slow_provider_requests < 0:
                raise ValueError(
                    "BASEBALL_MAX_SLOW_PROVIDER_REQUESTS cannot be negative"
                )

            slow_provider = {
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
            if (
                execution_mode == "SCHEDULED"
                and slow_provider_enabled
                and client.remaining_budget > 0
                and max_slow_provider_requests > 0
            ):
                slow_repository = PostgreSQLProviderDataRepository(connection)
                slow_provider = collect_slow_provider_data(
                    client,
                    slow_repository,
                    now=cycle_now,
                    max_requests=min(
                        max_slow_provider_requests,
                        client.remaining_budget,
                    ),
                    league_id=1,
                    season=cycle_now.year,
                )

            game_history = {
                "requests": 0,
                "calls": 0,
                "rows": 0,
                "inserted": 0,
                "errors": 0,
            }
            slow_requests_used = int(slow_provider["requests"])
            history_request_cap = max(
                0,
                max_slow_provider_requests - slow_requests_used,
            )
            if (
                execution_mode == "SCHEDULED"
                and slow_provider_enabled
                and client.remaining_budget > 0
                and history_request_cap > 0
            ):
                history_repository = PostgreSQLGameHistoryRepository(connection)
                game_history = collect_game_history(
                    client,
                    history_repository,
                    now=cycle_now,
                    max_requests=min(
                        history_request_cap,
                        client.remaining_budget,
                    ),
                    league_id=1,
                    season=cycle_now.year,
                )

            summary["slow_provider_enabled"] = int(slow_provider_enabled)
            summary["slow_provider_requests"] = int(slow_provider["requests"])
            summary["slow_standings_calls"] = int(slow_provider["standings_calls"])
            summary["slow_standings_inserted"] = int(
                slow_provider["standings_inserted"]
            )
            summary["slow_team_statistics_calls"] = int(
                slow_provider["team_statistics_calls"]
            )
            summary["slow_team_statistics_inserted"] = int(
                slow_provider["team_statistics_inserted"]
            )
            summary["slow_team_statistics_due_uncollected"] = int(
                slow_provider["team_statistics_due_uncollected"]
            )
            summary["slow_catalog_calls"] = int(slow_provider["catalog_calls"])
            summary["slow_catalogs_inserted"] = int(slow_provider["catalogs_inserted"])
            summary["game_history_requests"] = int(game_history["requests"])
            summary["game_history_calls"] = int(game_history["calls"])
            summary["game_history_rows"] = int(game_history["rows"])
            summary["game_history_inserted"] = int(game_history["inserted"])

            mlb_identity_enabled = os.getenv(
                "BASEBALL_ENABLE_MLB_IDENTITY_BOOTSTRAP", "false"
            ).strip().lower() in {"1", "true", "yes", "on"}
            mlb_identity_date = os.getenv(
                "BASEBALL_MLB_IDENTITY_DATE",
                cycle_now.date().isoformat(),
            ).strip()
            mlb_identity_version = os.getenv(
                "BASEBALL_MLB_IDENTITY_MAPPING_VERSION",
                f"mlb-{cycle_now.year}-v1",
            ).strip()
            mlb_identity = {
                "status": "DISABLED",
                "schedule_calls": 0,
                "fixtures_seen": 0,
                "fixtures_already_linked": 0,
                "team_mappings_before": 0,
                "team_mappings_inserted": 0,
                "team_mappings_total": 0,
                "game_links_inserted": 0,
                "game_links_total_for_target": 0,
                "mapping_failures": 0,
                "link_failures": 0,
                "ready_for_enrichment": 0,
            }
            if execution_mode == "SCHEDULED" and mlb_identity_enabled:
                identity_repository = PostgreSQLMLBIdentityRepository(connection)
                identity_client = OfficialMLBStatsClient(raw_archive=archive)
                mlb_identity = collect_mlb_identity_bootstrap(
                    identity_client,
                    identity_repository,
                    date_iso=mlb_identity_date,
                    mapping_version=mlb_identity_version,
                    now=cycle_now,
                )

            summary["mlb_identity_enabled"] = int(mlb_identity_enabled)
            summary["mlb_identity_status"] = str(mlb_identity["status"])
            summary["mlb_identity_schedule_calls"] = int(
                mlb_identity["schedule_calls"]
            )
            summary["mlb_identity_fixtures_seen"] = int(
                mlb_identity["fixtures_seen"]
            )
            summary["mlb_identity_fixtures_already_linked"] = int(
                mlb_identity["fixtures_already_linked"]
            )
            summary["mlb_identity_team_mappings_inserted"] = int(
                mlb_identity["team_mappings_inserted"]
            )
            summary["mlb_identity_team_mappings_total"] = int(
                mlb_identity["team_mappings_total"]
            )
            summary["mlb_identity_game_links_inserted"] = int(
                mlb_identity["game_links_inserted"]
            )
            summary["mlb_identity_game_links_total_for_target"] = int(
                mlb_identity["game_links_total_for_target"]
            )
            summary["mlb_identity_mapping_failures"] = int(
                mlb_identity["mapping_failures"]
            )
            summary["mlb_identity_link_failures"] = int(
                mlb_identity["link_failures"]
            )
            summary["mlb_identity_ready_for_enrichment"] = int(
                mlb_identity["ready_for_enrichment"]
            )
            summary["errors"] = (
                int(summary["errors"])
                + int(slow_provider["errors"])
                + int(game_history["errors"])
            )
            summary["api_requests"] = client.request_count
            summary["api_remaining"] = client.remaining_budget
            summary["fixture_observations_inserted"] = (
                int(summary["fixture_observations_inserted"])
                + int(settlement["fixture_observations_inserted"])
                + int(monitoring["fixture_observations_inserted"])
            )
            summary["odds_calls"] = int(summary["odds_calls"]) + int(
                monitoring["odds_calls"]
            )
            summary["canonical_rows"] = int(summary["canonical_rows"]) + int(
                monitoring["canonical_rows"]
            )
            summary["observations_inserted"] = int(
                summary["observations_inserted"]
            ) + int(monitoring["observations_inserted"])
            summary["errors"] = (
                int(summary["errors"])
                + int(settlement["errors"])
                + int(monitoring["errors"])
            )
            summary["settlement_due_picks"] = int(settlement["due_picks"])
            summary["settlement_game_calls"] = int(settlement["game_calls"])
            summary["settlement_result_facts_inserted"] = int(
                settlement["result_facts_inserted"]
            )
            summary["settlements"] = int(settlement["settlements"])
            summary["settlement_wins"] = int(settlement["wins"])
            summary["settlement_losses"] = int(settlement["losses"])
            summary["settlement_pushes"] = int(settlement["pushes"])
            summary["settlement_clv_available"] = int(settlement["clv_available"])
            summary["settlement_clv_unavailable"] = int(settlement["clv_unavailable"])
            summary["settlement_nonterminal"] = int(settlement["nonterminal"])
            summary["monitoring_started"] = int(monitoring["monitoring_started"])
            summary["monitoring_due_picks"] = int(monitoring["due_picks"])
            summary["monitoring_fixture_calls"] = int(monitoring["fixture_calls"])
            summary["monitoring_odds_calls"] = int(monitoring["odds_calls"])
            summary["monitoring_finalizations"] = int(monitoring["finalizations"])
            summary["monitoring_closing_captured"] = int(monitoring["closing_captured"])
            summary["monitoring_closing_stale"] = int(monitoring["closing_stale"])
            summary["monitoring_closing_no_valid_quote"] = int(
                monitoring["closing_no_valid_quote"]
            )
            summary["cycle_id"] = cycle_id
            summary["execution_mode"] = execution_mode
            summary["cycle_request_cap"] = effective_request_cap
            repository.append_collection_cycle(
                CollectionCycle.from_summary(
                    cycle_id=cycle_id,
                    started_at=cycle_started_at,
                    finished_at=datetime.now(UTC),
                    summary=summary,
                    execution_mode=execution_mode,
                )
            )
            return summary
        finally:
            connection.execute(
                "SELECT pg_advisory_unlock(%s)",
                (_ADVISORY_LOCK_KEY,),
            )
