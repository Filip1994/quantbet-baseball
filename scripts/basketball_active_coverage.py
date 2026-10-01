from __future__ import annotations

import json, os
from datetime import date
from urllib.request import Request, urlopen

BASE_URL = os.getenv("API_BASKETBALL_BASE_URL", "https://v1.basketball.api-sports.io").rstrip("/")
API_KEY = (os.getenv("API_BASKETBALL_KEY") or os.getenv("API_BASEBALL_KEY") or "").strip()

req = Request(
    BASE_URL + "/leagues",
    headers={"x-apisports-key": API_KEY, "Accept": "application/json"},
)
with urlopen(req, timeout=20) as r:
    payload = json.loads(r.read().decode("utf-8"))

today = date.today()
active = []
for league in payload.get("response", []):
    for season in league.get("seasons") or []:
        start = season.get("start")
        end = season.get("end")
        if not start or not end:
            continue
        try:
            s = date.fromisoformat(start)
            e = date.fromisoformat(end)
        except ValueError:
            continue
        if not (s <= today <= e):
            continue
        coverage = season.get("coverage") or {}
        stats = ((coverage.get("games") or {}).get("statistics") or {})
        row = {
            "league_id": league.get("id"),
            "league": league.get("name"),
            "country": (league.get("country") or {}).get("name"),
            "season": season.get("season"),
            "odds": bool(coverage.get("odds")),
            "team_stats": bool(stats.get("teams")),
            "player_stats": bool(stats.get("players")),
            "standings": bool(coverage.get("standings")),
            "players": bool(coverage.get("players")),
        }
        if row["odds"] and row["team_stats"]:
            active.append(row)

active.sort(key=lambda x: (x["country"] or "", x["league"] or ""))
print(json.dumps({
    "stage": "active_full_coverage",
    "date": str(today),
    "count": len(active),
    "leagues": active,
}, ensure_ascii=False))
