from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return default


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def main() -> None:
    root = Path(".")
    snapshots = []
    for path in sorted((root / "data" / "baseball" / "snapshots").glob("*.jsonl")):
        snapshots.extend(load_jsonl(path))
    observations = load_jsonl(root / "data" / "baseball" / "market_observations.jsonl")
    signals = load_json(root / "baseball_intraday_signals.json", [])
    scheduler = load_json(root / "data" / "baseball" / "scheduler_state.json", {})

    latest_by_game: dict[str, dict[str, Any]] = {}
    for row in snapshots:
        game_id = row.get("game_id")
        if game_id is not None:
            latest_by_game[str(game_id)] = row
    active = []
    now = datetime.now(UTC)
    for row in latest_by_game.values():
        kickoff_raw = row.get("kickoff")
        if not kickoff_raw:
            continue
        try:
            kickoff = datetime.fromisoformat(str(kickoff_raw)).astimezone(UTC)
        except ValueError:
            continue
        if -180 <= (kickoff - now).total_seconds() / 60 <= 36 * 60:
            state = scheduler.get("events", {}).get(str(row.get("game_id")), {})
            active.append({
                "game_id": row.get("game_id"),
                "league": row.get("league"),
                "match": f"{row.get('away', '')} @ {row.get('home', '')}",
                "kickoff": kickoff.isoformat(),
                "last_observation_at": state.get("last_observation_at") or row.get("captured_at"),
                "cadence_minutes": state.get("cadence_minutes"),
                "priority": state.get("priority"),
            })
    active.sort(key=lambda x: x["kickoff"])

    bookmaker_counter = Counter(str(row.get("bookmaker_name")) for row in observations if row.get("bookmaker_name"))
    market_counter = Counter(str(row.get("market")) for row in observations if row.get("market"))
    latest_capture = max((row.get("captured_at", "") for row in snapshots), default=None)
    payload = {
        "contract_version": "1.0",
        "generated_at": now.isoformat(),
        "system": {"status": "HEALTHY" if latest_capture else "NO_DATA", "paper_mode": True},
        "overview": {
            "events_observed": len(latest_by_game),
            "active_events": len(active),
            "observations": len(observations),
            "strong_signals": len([s for s in signals if s.get("status") in {"PAPER_SIGNAL", "STRONG_SIGNAL"}]),
            "production": len([s for s in signals if s.get("status") == "PAPER_SIGNAL"]),
            "bookmakers": len(bookmaker_counter),
            "markets": len(market_counter),
        },
        "freshness": {"last_successful_collection": latest_capture, "current_observation_age_seconds": None},
        "api": {"daily_ceiling": 7104, "daily_subscription": 7500, "headroom": 396},
        "live_watchlist": active[:50],
        "production": [s for s in signals if s.get("status") == "PAPER_SIGNAL"][:50],
        "strong_signals": [s for s in signals if s.get("status") in {"PAPER_SIGNAL", "STRONG_SIGNAL"}][:50],
        "market_intelligence": {
            "top_bookmakers": bookmaker_counter.most_common(20),
            "top_markets": market_counter.most_common(30),
        },
    }
    out = root / "data" / "baseball" / "dashboard.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
