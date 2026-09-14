from __future__ import annotations

import unittest

from quantbot.baseball.run_model import poisson_moneyline_probabilities


class PoissonRunModelTests(unittest.TestCase):
    def test_equal_expected_runs_produce_symmetric_probabilities(self) -> None:
        result = poisson_moneyline_probabilities(4.5, 4.5)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertAlmostEqual(result[0], 0.5, places=10)
        self.assertAlmostEqual(result[1], 0.5, places=10)

    def test_higher_home_expectation_increases_home_probability(self) -> None:
        result = poisson_moneyline_probabilities(5.0, 3.0)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertGreater(result[0], result[1])
        self.assertAlmostEqual(sum(result), 1.0, places=12)

    def test_invalid_inputs_fail_closed(self) -> None:
        self.assertIsNone(poisson_moneyline_probabilities(0, 3.0))
        self.assertIsNone(poisson_moneyline_probabilities(float("nan"), 3.0))
        self.assertIsNone(poisson_moneyline_probabilities(3.0, 4.0, max_runs=10))

    def test_result_is_two_way_and_finite(self) -> None:
        result = poisson_moneyline_probabilities(1.2, 7.8)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(all(0.0 < probability < 1.0 for probability in result))
        self.assertAlmostEqual(sum(result), 1.0, places=12)


if __name__ == "__main__":
    unittest.main()
