"""Bounded one-shot live audit of the API-Sports Baseball provider surface."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import psycopg

from .api import BaseballAPIClient, BaseballAPIError
from .config import BaseballSettings
from .db import database_url_from_env
from .raw_archive import archive_from_env


def _keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        return sorted(str(key) for key in value)
    return []


def _shape(value: Any, *, depth: int = 0, max_depth: int = 4) -> Any:
    if depth >= max_depth:
        if isinstance(value, list):
            return {"type": "list", "count": len(value)}
        if isinstance(value, dict):
            return {"type": "object", "keys": _keys(value)}
        return type(value).__name__

    if isinstance(value, list):
        return {
            "type": "list",
            "count": len(value),
            "first": _shape(value[0], depth=depth + 1, max_depth=max_depth)
            if value
            else None,
        }
    if isinstance(value, dict):
        return {
            key: _shape(item, depth=depth + 1, max_depth=max_depth)
            for key, item in sorted(value.items())
        }
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, str)):
        return value
    return type(value).__name__


def _compact_sample(row: Any) -> Any:
    if isinstance(row, dict):
        return _shape(row, max_depth=4)
    return _shape(row, max_depth=3)


def already_completed(audit_id: str) -> bool:
    with psycopg.connect(database_url_from_env()) as connection:
        row = connection.execute(
            "SELECT 1 FROM runtime_cycles "
            "WHERE stats->>'provider_surface_audit_id' = %s LIMIT 1",
            (audit_id,),
        ).fetchone()
    return row is not None


def run_provider_surface_audit(
    root: Path,
    *,
    audit_id: str,
    season: int,
) -> dict[str, Any]:
    if already_completed(audit_id):
        return {
            "status": "ALREADY_DONE",
            "provider_surface_audit_id": audit_id,
            "provider_requests": 0,
        }

    settings = BaseballSettings.from_env(root)
    archive = archive_from_env(settings.raw_archive_dir, require_remote=True)
    client = BaseballAPIClient(
        replace(
            settings,
            api_request_budget=12,
            api_max_attempts=1,
        ),
        raw_archive=archive,
    )

    results: dict[str, Any] = {}
    archive_receipts: dict[str, Any] = {}

    def call(
        name: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        *,
        object_response: bool = False,
    ) -> list[dict[str, Any]]:
        try:
            if object_response:
                row, receipt = client.get_object_with_receipt(
                    endpoint,
                    params or {},
                    ttl_seconds=0,
                    use_cache=False,
                )
                rows = [row]
            else:
                rows, receipt = client.get_with_receipt(
                    endpoint,
                    params or {},
                    ttl_seconds=0,
                    use_cache=False,
                )
        except BaseballAPIError as exc:
            results[name] = {
                "status": "ERROR",
                "error": str(exc)[:800],
            }
            return []

        results[name] = {
            "status": "OK",
            "rows": len(rows),
            "sample": _compact_sample(rows[0]) if rows else None,
        }
        if receipt is not None:
            archive_receipts[name] = {
                "ref": receipt.ref,
                "checksum": receipt.checksum,
                "captured_at": receipt.captured_at,
            }
        return rows

    call(
        "standings_mlb",
        "standings",
        {"league": 1, "season": season},
    )
    call(
        "standings_npb",
        "standings",
        {"league": 2, "season": season},
    )

    mlb_team_rows = call(
        "team_stats_mlb_id_contract",
        "teams/statistics",
        {"id": 22, "season": season},
    )
    if not mlb_team_rows:
        call(
            "team_stats_mlb_team_contract",
            "teams/statistics",
            {"team": 22, "league": 1, "season": season},
            object_response=True,
        )

    npb_team_rows = call(
        "team_stats_npb_id_contract",
        "teams/statistics",
        {"id": 58, "season": season},
    )
    if not npb_team_rows:
        call(
            "team_stats_npb_team_contract",
            "teams/statistics",
            {"team": 58, "league": 2, "season": season},
            object_response=True,
        )

    player_rows = call(
        "players_search_ohtani",
        "players",
        {"search": "ohtani"},
    )
    player_id: int | None = None
    if player_rows:
        first = player_rows[0]
        candidate = first.get("id") if isinstance(first, dict) else None
        if isinstance(candidate, int):
            player_id = candidate
        elif isinstance(first, dict):
            player = first.get("player")
            candidate = player.get("id") if isinstance(player, dict) else None
            if isinstance(candidate, int):
                player_id = candidate

    if player_id is not None:
        call(
            "player_statistics_ohtani",
            "players/statistics",
            {"id": player_id, "season": season},
        )
    else:
        results["player_statistics_ohtani"] = {
            "status": "SKIPPED",
            "reason": "NO_PLAYER_ID_FROM_SEARCH",
        }

    call("odds_bets", "odds/bets")
    call("odds_bookmakers", "odds/bookmakers")

    return {
        "status": "COMPLETE",
        "provider_surface_audit_id": audit_id,
        "season": season,
        "provider_requests": client.request_count,
        "request_cap": 12,
        "results": results,
        "archive_receipts": archive_receipts,
    }
