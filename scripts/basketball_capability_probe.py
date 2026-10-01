from __future__ import annotations

import json
import os
from datetime import date, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = os.getenv("API_BASKETBALL_BASE_URL", "https://v1.basketball.api-sports.io").rstrip("/")
API_KEY = (os.getenv("API_BASKETBALL_KEY") or os.getenv("API_BASEBALL_KEY") or "").strip()
MAX_REQUESTS = int(os.getenv("BASKETBALL_AUDIT_MAX_REQUESTS", "12"))

request_count = 0


def api_get(endpoint: str, **params):
    global request_count
    if not API_KEY:
        raise RuntimeError("Set API_BASKETBALL_KEY or API_BASEBALL_KEY")
    if request_count >= MAX_REQUESTS:
        raise RuntimeError(f"Audit request cap reached: {MAX_REQUESTS}")

    query = urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    if query:
        url += f"?{query}"

    req = Request(url, headers={"x-apisports-key": API_KEY, "Accept": "application/json"})
    request_count += 1
    with urlopen(req, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if payload.get("errors"):
        raise RuntimeError(f"{endpoint} API error: {payload['errors']}")
    return payload.get("response", []), payload


def score_shape(game: dict) -> dict:
    scores = game.get("scores") or {}
    return {
        "game_id": game.get("id"),
        "league": (game.get("league") or {}).get("name"),
        "date": game.get("date"),
        "status": (game.get("status") or {}).get("short"),
        "scores": scores,
        "has_quarter_keys": any(k in scores for k in ("quarter_1", "quarter_2", "quarter_3", "quarter_4")),
    }


def odds_inventory(item: dict) -> dict:
    out = []
    for bookmaker in item.get("bookmakers") or []:
        bets = bookmaker.get("bets") or []
        out.append({
            "bookmaker_id": bookmaker.get("id"),
            "bookmaker": bookmaker.get("name"),
            "markets": [
                {
                    "id": bet.get("id"),
                    "name": bet.get("name"),
                    "value_count": len(bet.get("values") or []),
                    "sample_values": (bet.get("values") or [])[:6],
                }
                for bet in bets
            ],
        })
    return {"game_id": item.get("game", {}).get("id") or item.get("id"), "bookmakers": out}


def main():
    today = date.today()

    leagues, _ = api_get("leagues")
    print(json.dumps({
        "stage": "leagues",
        "request_count": request_count,
        "league_count": len(leagues),
        "sample": leagues[:10],
    }, ensure_ascii=False))

    completed = []
    # Free API-Basketball access is date-window limited. Stay strictly within
    # yesterday/today so the capability audit does not waste requests.
    for target_date in (today - timedelta(days=1), today):
        games, _ = api_get("games", date=str(target_date))
        finished = [g for g in games if ((g.get("status") or {}).get("short") in {"FT", "AOT"})]
        completed.extend(finished[:5])
        if len(completed) >= 5:
            break

    print(json.dumps({
        "stage": "historical_score_shapes",
        "request_count": request_count,
        "games": [score_shape(g) for g in completed[:5]],
    }, ensure_ascii=False))

    upcoming = []
    # Free window currently permits today and tomorrow.
    for target_date in (today, today + timedelta(days=1)):
        games, _ = api_get("games", date=str(target_date))
        scheduled = [g for g in games if ((g.get("status") or {}).get("short") in {"NS", "TBD"})]
        upcoming.extend(scheduled[:5])
        if upcoming:
            break

    odds_results = []
    for game in upcoming[:3]:
        game_id = game.get("id")
        if not game_id:
            continue
        odds, _ = api_get("odds", game=game_id)
        for item in odds[:2]:
            odds_results.append(odds_inventory(item))

    print(json.dumps({
        "stage": "odds_market_inventory",
        "request_count": request_count,
        "upcoming_games_checked": [g.get("id") for g in upcoming[:3]],
        "results": odds_results,
    }, ensure_ascii=False))

    print(json.dumps({
        "stage": "summary",
        "requests_used": request_count,
        "request_cap": MAX_REQUESTS,
        "goal": "Verify quarter score structure and discover pre-match FT/HT/Q1/Q2/Q3/Q4 total markets before building QuantBet Basketball.",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
