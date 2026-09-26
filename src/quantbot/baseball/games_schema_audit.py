"""One-shot live /games schema audit using the service's own hidden API key."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

import psycopg

from .api import BaseballAPIClient
from .config import BaseballSettings
from .db import database_url_from_env
from .raw_archive import archive_from_env


def _keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        return sorted(str(key) for key in value)
    return []


def summarize_games(rows: list[dict[str, Any]]) -> dict[str, Any]:
    league_counts: Counter[str] = Counter()
    league_ids: dict[str, int | None] = {}
    samples: dict[str, dict[str, Any]] = {}

    for row in rows:
        league = row.get("league") if isinstance(row, dict) else None
        league_name = str((league or {}).get("name") or "UNKNOWN")
        league_id = (league or {}).get("id")
        league_counts[league_name] += 1
        league_ids.setdefault(
            league_name,
            league_id if isinstance(league_id, int) else None,
        )
        if league_name not in samples:
            teams = row.get("teams") or {}
            samples[league_name] = {
                "game_id": row.get("id"),
                "date": row.get("date"),
                "time": row.get("time"),
                "timezone": row.get("timezone"),
                "status": row.get("status"),
                "home": (
                    (teams.get("home") or {}).get("name")
                    if isinstance(teams, dict)
                    else None
                ),
                "away": (
                    (teams.get("away") or {}).get("name")
                    if isinstance(teams, dict)
                    else None
                ),
                "top_level_keys": _keys(row),
                "league_keys": _keys(row.get("league")),
                "country_keys": _keys(row.get("country")),
                "teams_keys": _keys(row.get("teams")),
                "home_team_keys": _keys(
                    (teams or {}).get("home") if isinstance(teams, dict) else None
                ),
                "away_team_keys": _keys(
                    (teams or {}).get("away") if isinstance(teams, dict) else None
                ),
                "status_keys": _keys(row.get("status")),
                "scores_keys": _keys(row.get("scores")),
                "optional_fields_present": {
                    name: bool(row.get(name))
                    for name in (
                        "venue",
                        "stadium",
                        "pitchers",
                        "lineups",
                        "injuries",
                        "weather",
                        "umpire",
                        "players",
                    )
                },
            }

    mlb = samples.get("MLB")
    non_mlb_names = [name for name in samples if name != "MLB"][:5]

    return {
        "results_count": len(rows),
        "league_counts": [
            {
                "league": name,
                "league_id": league_ids.get(name),
                "games": count,
            }
            for name, count in sorted(league_counts.items())
        ],
        "mlb_sample": mlb,
        "non_mlb_samples": [samples[name] | {"league": name} for name in non_mlb_names],
        "mlb_present": mlb is not None,
        "non_mlb_league_count": len([name for name in samples if name != "MLB"]),
    }


def already_completed(audit_id: str) -> bool:
    with psycopg.connect(database_url_from_env()) as connection:
        row = connection.execute(
            "SELECT 1 FROM runtime_cycles "
            "WHERE stats->>'games_schema_audit_id' = %s LIMIT 1",
            (audit_id,),
        ).fetchone()
    return row is not None


def run_games_schema_audit(
    root: Path,
    *,
    audit_id: str,
    date_iso: str,
) -> dict[str, Any]:
    if already_completed(audit_id):
        return {
            "status": "ALREADY_DONE",
            "games_schema_audit_id": audit_id,
            "provider_requests": 0,
        }

    settings = BaseballSettings.from_env(root)
    archive = archive_from_env(settings.raw_archive_dir, require_remote=True)
    client = BaseballAPIClient(
        replace(
            settings,
            api_request_budget=1,
            api_max_attempts=1,
        ),
        raw_archive=archive,
    )
    rows, receipt = client.games_by_date_with_receipt(date_iso)

    summary = summarize_games(rows)
    return {
        "status": "COMPLETE",
        "games_schema_audit_id": audit_id,
        "date": date_iso,
        "provider_requests": client.request_count,
        "raw_archive_ref": receipt.ref,
        "raw_archive_checksum": receipt.checksum,
        **summary,
    }
