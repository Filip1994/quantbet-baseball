from __future__ import annotations

import unittest

from quantbot.baseball.market import aggregate_bookmaker_probabilities, devig_two_way


class MarketMathContractTests(unittest.TestCase):
    def test_devig_normalizes_two_way_overround(self) -> None:
        result = devig_two_way(0.60, 0.50)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertAlmostEqual(result[0], 0.60 / 1.10)
        self.assertAlmostEqual(result[1], 0.50 / 1.10)
        self.assertAlmostEqual(sum(result), 1.0)

    def test_devig_rejects_invalid_or_missing_inputs(self) -> None:
        self.assertIsNone(devig_two_way(None, 0.5))
        self.assertIsNone(devig_two_way(0.0, 0.5))
        self.assertIsNone(devig_two_way(float("nan"), 0.5))

    def test_aggregation_is_not_weighted_by_number_of_duplicate_rows(self) -> None:
        result = aggregate_bookmaker_probabilities(
            [
                {"side": "home", "probability": 0.60},
                {"side": "away", "probability": 0.50},
                {"side": "home", "probability": 0.60},
                {"side": "away", "probability": 0.50},
            ]
        )
        self.assertEqual(result, {"home": 0.6 / 1.1, "away": 0.5 / 1.1})

    def test_incomplete_market_fails_closed(self) -> None:
        self.assertIsNone(aggregate_bookmaker_probabilities([{"side": "home", "probability": 0.6}]))


if __name__ == "__main__":
    unittest.main()
