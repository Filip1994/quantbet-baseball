from __future__ import annotations

import math
from typing import Any


def _probability(value: Any) -> float | None:
    try:
        probability = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(probability) or not 0.0 < probability < 1.0:
        return None
    return probability


def fair_decimal_odds(probability: Any) -> float | None:
    """Return fair decimal odds for a valid two-way probability."""
    parsed = _probability(probability)
    if parsed is None:
        return None
    return 1.0 / parsed


def expected_value_per_unit(model_probability: Any, decimal_odds: Any) -> float | None:
    """Return expected profit per one unit staked, net of stake."""
    probability = _probability(model_probability)
    try:
        odds = float(decimal_odds)
    except (TypeError, ValueError):
        return None
    if probability is None or not math.isfinite(odds) or odds <= 1.0:
        return None
    value = probability * (odds - 1.0) - (1.0 - probability)
    return value if math.isfinite(value) else None


def edge(model_probability: Any, market_probability: Any) -> float | None:
    """Return model probability minus market probability."""
    model = _probability(model_probability)
    market = _probability(market_probability)
    if model is None or market is None:
        return None
    result = model - market
    return result if math.isfinite(result) else None
