from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .api import BaseballAPIClient, BaseballAPIError
from .config import BaseballSettings


def _normalise(game: dict[str, Any], captured_at: str) -> dict[str, Any]:
    teams = game.get("teams") or {}
    scores = game.get("scores") or {}
    status = game.get("status") or {}
    home = teams.get("home") or game.get("home")
    away = teams.get("away") or game.get("away")
    return {
        "game_id": game.get("id", game.get("game_id")),
        "date": game.get("date"),
        "home": home,
        "away": away,
        "scores": scores,
        "status": status.get("short") if isinstance(status, dict) else status,
        "status_long": status.get("long") if isinstance(status, dict) else None,
        "captured_at": captured_at,
        "source": "api-sports-baseball/games",
    }


def collect_results(
    root: Path, dates: Iterable[str], output_path: Path
) -> dict[str, int]:
    requested_dates = sorted(set(dates))
    settings = BaseballSettings.from_env(root)
    client = BaseballAPIClient(settings)
    captured_at = datetime.now(UTC).isoformat()
    rows: list[dict[str, Any]] = []
    errors = 0

    for date_iso in requested_dates:
        try:
            rows.extend(
                _normalise(game, captured_at)
                for game in client.games_by_date(date_iso)
            )
        except BaseballAPIError:
            errors += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            )

    return {
        "dates": len(requested_dates),
        "games": len(rows),
        "api_requests": client.request_count,
        "errors": errors,
    }
