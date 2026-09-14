from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any


def _finite_probability(value: Any) -> float | None:
    try:
        probability = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(probability) or not 0.0 < probability < 1.0:
        return None
    return probability


def devig_two_way(home_probability: Any, away_probability: Any) -> tuple[float, float] | None:
    """Normalize a valid two-way market pair by removing the overround.

    This is a proportional normalization only. It is deliberately limited to
    two mutually exclusive outcomes and does not infer missing probabilities.
    """
    home = _finite_probability(home_probability)
    away = _finite_probability(away_probability)
    if home is None or away is None:
        return None
    total = home + away
    if not math.isfinite(total) or total <= 0.0:
        return None
    return home / total, away / total


def aggregate_bookmaker_probabilities(rows: Iterable[dict[str, Any]]) -> dict[str, float] | None:
    """Return a bookmaker-neutral mean of already de-vigged two-way prices.

    Each input row must contain ``side`` and ``probability``. Both sides must
    be present at least once. Invalid rows are ignored; an incomplete result
    returns ``None`` rather than manufacturing a market estimate.
    """
    buckets: dict[str, list[float]] = {"home": [], "away": []}
    for row in rows:
        side = str(row.get("side") or "").casefold()
        probability = _finite_probability(row.get("probability"))
        if side in buckets and probability is not None:
            buckets[side].append(probability)
    if not buckets["home"] or not buckets["away"]:
        return None
    home = sum(buckets["home"]) / len(buckets["home"])
    away = sum(buckets["away"]) / len(buckets["away"])
    normalized = devig_two_way(home, away)
    if normalized is None:
        return None
    return {"home": normalized[0], "away": normalized[1]}
