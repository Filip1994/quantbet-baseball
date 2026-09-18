from __future__ import annotations

import math
from typing import Any

from .decision import evaluate_moneyline_decision


def build_moneyline_signal(
    game_id: Any,
    home_model_probability: Any,
    away_model_probability: Any,
    home_market_probability: Any,
    away_market_probability: Any,
    home_decimal_odds: Any,
    away_decimal_odds: Any,
    *,
    min_edge: float = 0.02,
    min_expected_value: float = 0.0,
    uncertainty_approved: bool = False,
) -> dict[str, Any]:
    """Evaluate both sides of one pre-game moneyline and select at most one.

    This is an audit-friendly signal builder, not an execution component.
    Invalid identity or non-finite model inputs produce an abstention.
    """
    result: dict[str, Any] = {
        "game_id": game_id,
        "decision": "PASS",
        "reason": "invalid_input",
        "selected_side": None,
        "home": None,
        "away": None,
    }
    if not isinstance(game_id, str) or not game_id.strip():
        return result

    try:
        model_home = float(home_model_probability)
        model_away = float(away_model_probability)
    except (TypeError, ValueError):
        return result
    if (
        not math.isfinite(model_home)
        or not math.isfinite(model_away)
        or not math.isclose(model_home + model_away, 1.0, rel_tol=0.0, abs_tol=1e-9)
    ):
        result["reason"] = "model_probabilities_not_two_way"
        return result

    home = evaluate_moneyline_decision(
        model_home,
        home_market_probability,
        home_decimal_odds,
        min_edge=min_edge,
        min_expected_value=min_expected_value,
        uncertainty_approved=uncertainty_approved,
    )
    away = evaluate_moneyline_decision(
        model_away,
        away_market_probability,
        away_decimal_odds,
        min_edge=min_edge,
        min_expected_value=min_expected_value,
        uncertainty_approved=uncertainty_approved,
    )
    result["home"] = home
    result["away"] = away
    eligible = [
        ("home", home),
        ("away", away),
    ]
    bets = [
        (side, candidate)
        for side, candidate in eligible
        if candidate["decision"] == "BET"
    ]
    if not bets:
        result["reason"] = "no_side_passed_policy"
        return result

    selected_side, selected = max(
        bets,
        key=lambda item: (float(item[1]["expected_value"]), float(item[1]["edge"])),
    )
    result.update(
        {
            "decision": "BET",
            "reason": "best_eligible_side_selected",
            "selected_side": selected_side,
        }
    )
    return result
