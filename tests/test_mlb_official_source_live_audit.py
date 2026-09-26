"""Bounded live audit of official MLB public structured sources.

Audit-only. This file is intentionally not production ingestion code.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
import warnings
from datetime import UTC, datetime, timedelta

BASE = "https://statsapi.mlb.com/api"


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
        "/v1/schedule",
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

    feed = _get(f"/v1.1/game/{game_pk}/feed/live")
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
        "/v1/transactions",
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
        f"/v1/teams/{team_id}/roster",
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


def test_official_mlb_historical_timecode_replay_audit() -> None:
    schedule = _get(
        "/v1/schedule",
        {
            "sportId": "1",
            "date": "2026-09-20",
            "hydrate": "probablePitcher,team,venue",
        },
    )
    games = [
        game
        for date in (schedule.get("dates") or [])
        if isinstance(date, dict)
        for game in (date.get("games") or [])
        if isinstance(game, dict)
    ]
    assert games, "historical MLB schedule returned no games"

    game = games[0]
    game_pk = int(game["gamePk"])
    game_date = datetime.fromisoformat(str(game["gameDate"]).replace("Z", "+00:00"))
    requested_at = (game_date.astimezone(UTC) - timedelta(hours=2)).replace(
        microsecond=0
    )
    timecode = requested_at.strftime("%Y%m%d_%H%M%S")

    feed = _get(
        f"/v1.1/game/{game_pk}/feed/live",
        {"timecode": timecode},
    )
    game_data = feed.get("gameData") or {}
    live_data = feed.get("liveData") or {}
    boxscore = live_data.get("boxscore") or {}
    teams = boxscore.get("teams") or {}
    side_summary = {}
    for side in ("away", "home"):
        side_data = teams.get(side) or {}
        side_summary[side] = {
            "batting_order_count": len(side_data.get("battingOrder") or []),
            "players_count": len(side_data.get("players") or {}),
            "bullpen_count": len(side_data.get("bullpen") or []),
            "pitchers_count": len(side_data.get("pitchers") or []),
        }

    summary = {
        "game_pk": game_pk,
        "scheduled_game_date": game.get("gameDate"),
        "requested_timecode": timecode,
        "metadata_timestamp": (feed.get("metaData") or {}).get("timeStamp"),
        "status": game_data.get("status") or {},
        "probable_pitcher_sides": sorted((game_data.get("probablePitchers") or {})),
        "boxscore": side_summary,
        "plays_count": len((live_data.get("plays") or {}).get("allPlays") or []),
    }
    warnings.warn(
        "MLB_TIMECODE_AUDIT=" + json.dumps(summary, sort_keys=True), stacklevel=1
    )
