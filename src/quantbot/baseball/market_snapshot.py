from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from .market import aggregate_bookmaker_probabilities, devig_two_way


_REQUIRED_IDENTITY = ("game_id", "market", "captured_at", "kickoff")


def _decimal_probability(value: Any) -> float | None:
    try:
        odds = float(value)
    except (TypeError, ValueError):
        return None
    if odds <= 1.0:
        return None
    return 1.0 / odds


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def build_two_way_market_snapshot(
    observations: Iterable[dict[str, Any]],
) -> dict[str, Any] | None:
    """Build one auditable, pregame two-way snapshot.

    All usable observations must share one game, market, capture timestamp and
    kickoff. Duplicate bookmaker/side observations are accepted only when
    identical; conflicting duplicates fail closed instead of using
    last-write-wins behavior.
    """
    by_bookmaker: dict[str, dict[str, float]] = defaultdict(dict)
    metadata: dict[str, Any] = {}
    identity: dict[str, Any] = {}
    seen: dict[tuple[str, str], float] = {}

    for row in observations:
        side = str(row.get("side") or "").casefold()
        bookmaker = str(row.get("bookmaker_name") or row.get("bookmaker_id") or "").strip()
        probability = _decimal_probability(row.get("odds", row.get("odd")))
        if side not in {"home", "away"} or not bookmaker or probability is None:
            continue

        for field in _REQUIRED_IDENTITY:
            value = row.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                return None
            if field in identity and identity[field] != value:
                return None
            identity[field] = value

        captured = _parse_timestamp(identity["captured_at"])
        kickoff = _parse_timestamp(identity["kickoff"])
        if captured is None or kickoff is None or captured >= kickoff:
            return None

        key = (bookmaker, side)
        if key in seen and seen[key] != probability:
            return None
        seen[key] = probability
        by_bookmaker[bookmaker][side] = probability

        for field in ("league", "home", "away"):
            if field in row and field not in metadata:
                metadata[field] = row[field]

    if not identity:
        return None

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
        **identity,
        **metadata,
        "home_probability": aggregate["home"],
        "away_probability": aggregate["away"],
        "bookmakers_used": sorted({row["bookmaker_name"] for row in devigged}),
        "bookmaker_count": len({row["bookmaker_name"] for row in devigged}),
        "method": "bookmaker_level_proportional_devig_mean",
    }
