"""Bounded live audit of official MLB public structured sources.

Audit-only. This file is intentionally not production ingestion code.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
import warnings

BASE = "https://statsapi.mlb.com/api/v1"


def _get(path: str, params: dict[str, str] | None = None) -> dict:
    url = f"{BASE}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "quantbet-baseball-source-audit/2026-09-26"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        assert response.status == 200
        body = response.read(2_000_000)
    payload = json.loads(body)
    assert isinstance(payload, dict)
    return payload


def test_official_mlb_structured_source_audit() -> None:
    schedule = _get(
        "/schedule",
        {
            "sportId": "1",
            "date": "2026-09-26",
            "hydrate": "probablePitcher,team,venue",
        },
    )
    dates = schedule.get("dates") or []
    games = [
        game
        for date in dates
        if isinstance(date, dict)
        for game in (date.get("games") or [])
        if isinstance(game, dict)
    ]
    assert games, "MLB schedule returned no games for audit date"

    first = games[0]
    game_pk = int(first["gamePk"])
    schedule_summary = {
        "top_level_keys": sorted(schedule),
        "total_games": schedule.get("totalGames"),
        "game_keys": sorted(first),
        "game_pk": game_pk,
        "game_date": first.get("gameDate"),
        "status_keys": sorted(first.get("status") or {}),
        "venue": {
            "id": (first.get("venue") or {}).get("id"),
            "name": (first.get("venue") or {}).get("name"),
        },
        "teams": {},
    }
    for side in ("away", "home"):
        side_data = (first.get("teams") or {}).get(side) or {}
        team = side_data.get("team") or {}
        pitcher = side_data.get("probablePitcher") or {}
        schedule_summary["teams"][side] = {
            "team_id": team.get("id"),
            "team_name": team.get("name"),
            "probable_pitcher_id": pitcher.get("id"),
            "probable_pitcher_name": pitcher.get("fullName"),
            "side_keys": sorted(side_data),
        }

    feed = _get(f"/game/{game_pk}/feed/live")
    game_data = feed.get("gameData") or {}
    live_data = feed.get("liveData") or {}
    boxscore = live_data.get("boxscore") or {}
    feed_summary = {
        "top_level_keys": sorted(feed),
        "game_data_keys": sorted(game_data),
        "live_data_keys": sorted(live_data),
        "venue_keys": sorted(game_data.get("venue") or {}),
        "weather_keys": sorted(game_data.get("weather") or {}),
        "boxscore_keys": sorted(boxscore),
        "boxscore_team_keys": {
            side: sorted((boxscore.get("teams") or {}).get(side) or {})
            for side in ("away", "home")
        },
    }

    transactions = _get(
        "/transactions",
        {
            "startDate": "2026-09-24",
            "endDate": "2026-09-26",
            "sportId": "1",
        },
    )
    tx_rows = transactions.get("transactions") or []
    tx_summary = {
        "top_level_keys": sorted(transactions),
        "count": len(tx_rows),
        "row_keys": sorted(tx_rows[0])
        if tx_rows and isinstance(tx_rows[0], dict)
        else [],
    }

    team_id = schedule_summary["teams"]["home"]["team_id"]
    roster = _get(
        f"/teams/{team_id}/roster",
        {"rosterType": "active", "date": "2026-09-26"},
    )
    roster_rows = roster.get("roster") or []
    roster_summary = {
        "top_level_keys": sorted(roster),
        "count": len(roster_rows),
        "row_keys": sorted(roster_rows[0])
        if roster_rows and isinstance(roster_rows[0], dict)
        else [],
    }

    summary = {
        "source": "official MLB Stats API",
        "schedule": schedule_summary,
        "feed_live": feed_summary,
        "transactions": tx_summary,
        "active_roster": roster_summary,
    }
    warnings.warn(
        "MLB_SOURCE_AUDIT=" + json.dumps(summary, sort_keys=True), stacklevel=1
    )
