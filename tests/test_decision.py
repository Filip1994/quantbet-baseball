from __future__ import annotations

import unittest

from quantbot.baseball.decision import evaluate_moneyline_decision


class DecisionPolicyTests(unittest.TestCase):
    def test_valid_value_still_abstains_without_uncertainty_approval(self) -> None:
        result = evaluate_moneyline_decision(0.60, 0.50, 2.0)
        self.assertEqual(result["decision"], "PASS")
        self.assertEqual(result["reason"], "uncertainty_gate_not_met")
        self.assertAlmostEqual(result["edge"], 0.10)
        self.assertAlmostEqual(result["expected_value"], 0.20)

    def test_bet_when_all_gates_pass(self) -> None:
        result = evaluate_moneyline_decision(0.60, 0.50, 2.0, uncertainty_approved=True)
        self.assertEqual(result["decision"], "BET")
        self.assertEqual(result["reason"], "value_and_gates_passed")

    def test_edge_threshold_is_inclusive(self) -> None:
        result = evaluate_moneyline_decision(
            0.57, 0.55, 2.0, min_edge=0.02, uncertainty_approved=True
        )
        self.assertEqual(result["decision"], "BET")

    def test_invalid_input_fails_closed(self) -> None:
        result = evaluate_moneyline_decision(0.0, 0.50, 2.0, uncertainty_approved=True)
        self.assertEqual(result["decision"], "PASS")
        self.assertEqual(result["reason"], "invalid_input")

    def test_negative_threshold_is_rejected(self) -> None:
        result = evaluate_moneyline_decision(
            0.60, 0.50, 2.0, min_edge=-0.01, uncertainty_approved=True
        )
        self.assertEqual(result["decision"], "PASS")
        self.assertEqual(result["reason"], "invalid_input")


if __name__ == "__main__":
    unittest.main()
