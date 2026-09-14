from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from .market import aggregate_bookmaker_probabilities, devig_two_way


def _decimal_probability(value: Any) -> float | None:
    try:
        odds = float(value)
    except (TypeError, ValueError):
        return None
    if odds <= 1.0:
        return None
    return 1.0 / odds


def build_two_way_market_snapshot(
    observations: Iterable[dict[str, Any]],
) -> dict[str, Any] | None:
    """Build one conservative, bookmaker-neutral pregame two-way snapshot.

    Rows are grouped by bookmaker. A bookmaker contributes only when both
    home and away prices are present and valid. The final estimate is the
    normalized mean of bookmaker-level de-vigged probabilities.

    This function intentionally does not merge different capture times or
    infer missing outcomes. Callers must provide observations for one game,
    one market, and one capture timestamp.
    """
    by_bookmaker: dict[str, dict[str, float]] = defaultdict(dict)
    metadata: dict[str, Any] = {}
    for row in observations:
        side = str(row.get("side") or "").casefold()
        if side not in {"home", "away"}:
            continue
        bookmaker = str(row.get("bookmaker_name") or row.get("bookmaker_id") or "").strip()
        if not bookmaker:
            continue
        probability = _decimal_probability(row.get("odds", row.get("odd")))
        if probability is None:
            continue
        by_bookmaker[bookmaker][side] = probability
        for field in ("game_id", "captured_at", "kickoff", "league", "home", "away", "market"):
            if field in row and field not in metadata:
                metadata[field] = row[field]

    devigged: list[dict[str, Any]] = []
    for bookmaker, prices in by_bookmaker.items():
        pair = devig_two_way(prices.get("home"), prices.get("away"))
        if pair is not None:
            devigged.extend(
                [
                    {"bookmaker_name": bookmaker, "side": "home", "probability": pair[0]},
                    {"bookmaker_name": bookmaker, "side": "away", "probability": pair[1]},
                ]
            )

    aggregate = aggregate_bookmaker_probabilities(devigged)
    if aggregate is None:
        return None
    return {
        **metadata,
        "home_probability": aggregate["home"],
        "away_probability": aggregate["away"],
        "bookmakers_used": sorted({row["bookmaker_name"] for row in devigged}),
        "bookmaker_count": len({row["bookmaker_name"] for row in devigged}),
        "method": "bookmaker_level_proportional_devig_mean",
    }
