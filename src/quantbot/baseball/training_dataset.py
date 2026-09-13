from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
    return rows


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result > 1.0 else None


def _is_moneyline(market: Any) -> bool:
    text = str(market or "").lower()
    return any(token in text for token in ("moneyline", "match winner", "game winner", "winner")) and not any(
        token in text for token in ("run line", "spread", "total", "inning", "player", "strikeout", "hits")
    )


def _selection_side(selection: str, home: str, away: str) -> str | None:
    if selection.strip().casefold() == home.strip().casefold():
        return "home"
    if selection.strip().casefold() == away.strip().casefold():
        return "away"
    return None


def _result_map(results: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for game in results:
        game_id = game.get("game_id", game.get("id"))
        if game_id is None:
            continue
        home = game.get("home") or game.get("teams", {}).get("home", {})
        away = game.get("away") or game.get("teams", {}).get("away", {})
        scores = game.get("scores", {})
        home_name = home.get("name") if isinstance(home, dict) else home
        away_name = away.get("name") if isinstance(away, dict) else away
        home_score = scores.get("home") if isinstance(scores, dict) else None
        away_score = scores.get("away") if isinstance(scores, dict) else None
        status = str(game.get("status") or game.get("game", {}).get("status", {}).get("short") or "").lower()
        if home_score is None or away_score is None or home_score == away_score:
            continue
        if any(token in status for token in ("post", "cancel", "suspend", "abort")):
            continue
        mapped[str(game_id)] = {
            "home": home_name,
            "away": away_name,
            "home_score": home_score,
            "away_score": away_score,
            "status": status,
        }
    return mapped


def build_moneyline_rows(
    observations: Iterable[dict[str, Any]],
    results: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build pregame moneyline examples; final scores are labels only."""
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in observations:
        game_id = str(row.get("game_id", row.get("event_id", "")))
        if not game_id or not _is_moneyline(row.get("market")):
            continue
        odds = _number(row.get("odds", row.get("odd")))
        home, away = str(row.get("home") or ""), str(row.get("away") or "")
        side = _selection_side(str(row.get("selection") or ""), home, away)
        captured = _parse_time(row.get("captured_at"))
        kickoff = _parse_time(row.get("kickoff"))
        if odds is None or side is None or captured is None or kickoff is None or captured >= kickoff:
            continue
        result = results.get(game_id)
        if not result:
            continue
        winner = "home" if result["home_score"] > result["away_score"] else "away"
        key = (game_id, str(row.get("captured_at")), side)
        grouped[key].append({**row, "_odds": odds, "_side": side, "_winner": winner})

    output: list[dict[str, Any]] = []
    for rows in grouped.values():
        for row in rows:
            output.append(
                {
                    "game_id": str(row.get("game_id", row.get("event_id"))),
                    "captured_at": row["captured_at"],
                    "kickoff": row["kickoff"],
                    "league": row.get("league"),
                    "home": row.get("home"),
                    "away": row.get("away"),
                    "market": row.get("market"),
                    "selection": row.get("selection"),
                    "side": row["_side"],
                    "bookmaker_name": row.get("bookmaker_name"),
                    "odds": row["_odds"],
                    "implied_probability": 1.0 / row["_odds"],
                    "target": int(row["_side"] == row["_winner"]),
                    "result": row["_winner"],
                    "source_observation_id": row.get("observation_id"),
                }
            )
    return sorted(output, key=lambda item: (item["captured_at"], item["game_id"], item["selection"]))


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
    return count


def build_from_files(observations_path: Path, results_path: Path, output_path: Path) -> dict[str, int]:
    observations = _load_jsonl(observations_path)
    results = _result_map(_load_jsonl(results_path))
    rows = build_moneyline_rows(observations, results)
    written = write_jsonl(output_path, rows)
    return {"observations": len(observations), "resolved_games": len(results), "rows": written}
