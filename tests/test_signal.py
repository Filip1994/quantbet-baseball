from __future__ import annotations

import unittest

from quantbot.baseball.signal import build_moneyline_signal


class MoneylineSignalTests(unittest.TestCase):
    def _kwargs(self) -> dict[str, object]:
        return {
            "game_id": "game-1",
            "home_model_probability": 0.60,
            "away_model_probability": 0.40,
            "home_market_probability": 0.50,
            "away_market_probability": 0.50,
            "home_decimal_odds": 2.0,
            "away_decimal_odds": 2.0,
            "uncertainty_approved": True,
        }

    def test_selects_only_eligible_side(self) -> None:
        result = build_moneyline_signal(**self._kwargs())
        self.assertEqual(result["decision"], "BET")
        self.assertEqual(result["selected_side"], "home")

    def test_abstains_when_uncertainty_gate_is_missing(self) -> None:
        kwargs = self._kwargs()
        kwargs["uncertainty_approved"] = False
        result = build_moneyline_signal(**kwargs)
        self.assertEqual(result["decision"], "PASS")
        self.assertIsNone(result["selected_side"])

    def test_rejects_non_two_way_model_probabilities(self) -> None:
        kwargs = self._kwargs()
        kwargs["away_model_probability"] = 0.45
        result = build_moneyline_signal(**kwargs)
        self.assertEqual(result["decision"], "PASS")
        self.assertEqual(result["reason"], "model_probabilities_not_two_way")

    def test_rejects_missing_game_id(self) -> None:
        kwargs = self._kwargs()
        kwargs["game_id"] = ""
        result = build_moneyline_signal(**kwargs)
        self.assertEqual(result["decision"], "PASS")
        self.assertEqual(result["reason"], "invalid_input")


if __name__ == "__main__":
    unittest.main()
