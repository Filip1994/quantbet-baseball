from __future__ import annotations

import unittest

from quantbot.baseball.value import edge, expected_value_per_unit, fair_decimal_odds


class ValuePrimitiveTests(unittest.TestCase):
    def test_fair_decimal_odds(self) -> None:
        self.assertAlmostEqual(fair_decimal_odds(0.5), 2.0)

    def test_edge_is_model_minus_market(self) -> None:
        self.assertAlmostEqual(edge(0.60, 0.55), 0.05)

    def test_expected_value_is_net_of_stake(self) -> None:
        self.assertAlmostEqual(expected_value_per_unit(0.60, 2.0), 0.20)

    def test_invalid_values_fail_closed(self) -> None:
        self.assertIsNone(fair_decimal_odds(0))
        self.assertIsNone(edge(0.5, 1.0))
        self.assertIsNone(expected_value_per_unit(0.5, 1.0))
        self.assertIsNone(expected_value_per_unit(float("nan"), 2.0))


if __name__ == "__main__":
    unittest.main()
