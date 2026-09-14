from __future__ import annotations

import math
from typing import Any

from .value import edge, expected_value_per_unit, fair_decimal_odds


def evaluate_moneyline_decision(
    model_probability: Any,
    market_probability: Any,
    decimal_odds: Any,
    *,
    min_edge: float = 0.02,
    min_expected_value: float = 0.0,
    uncertainty_approved: bool = False,
) -> dict[str, Any]:
    """Evaluate a pre-game two-way moneyline candidate without placing a bet.

    The function is deliberately fail-closed and returns an auditable result.
    A candidate cannot receive ``BET`` status unless the explicit uncertainty
    gate is approved and both value thresholds are met.
    """
    result: dict[str, Any] = {
        "decision": "PASS",
        "reason": "invalid_input",
        "model_probability": None,
        "market_probability": None,
        "decimal_odds": None,
        "fair_decimal_odds": None,
        "edge": None,
        "expected_value": None,
        "min_edge": min_edge,
        "min_expected_value": min_expected_value,
        "uncertainty_approved": bool(uncertainty_approved),
    }

    try:
        edge_threshold = float(min_edge)
        ev_threshold = float(min_expected_value)
    except (TypeError, ValueError):
        return result
    if (
        not math.isfinite(edge_threshold)
        or not math.isfinite(ev_threshold)
        or edge_threshold < 0.0
    ):
        return result

    fair = fair_decimal_odds(model_probability)
    candidate_edge = edge(model_probability, market_probability)
    candidate_ev = expected_value_per_unit(model_probability, decimal_odds)
    try:
        odds = float(decimal_odds)
        model = float(model_probability)
        market = float(market_probability)
    except (TypeError, ValueError):
        return result
    if fair is None or candidate_edge is None or candidate_ev is None:
        return result

    result.update(
        {
            "model_probability": model,
            "market_probability": market,
            "decimal_odds": odds,
            "fair_decimal_odds": fair,
            "edge": candidate_edge,
            "expected_value": candidate_ev,
        }
    )

    if not uncertainty_approved:
        result["reason"] = "uncertainty_gate_not_met"
    elif candidate_edge < edge_threshold:
        result["reason"] = "edge_below_threshold"
    elif candidate_ev < ev_threshold:
        result["reason"] = "expected_value_below_threshold"
    else:
        result["decision"] = "BET"
        result["reason"] = "value_and_gates_passed"
    return result
