from __future__ import annotations

import unittest

from quantbot.baseball.training_dataset import _result_map, build_moneyline_rows


class TrainingDatasetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.result = _result_map([
            {
                "game_id": 101,
                "home": {"name": "Home Club"},
                "away": {"name": "Away Club"},
                "scores": {"home": 5, "away": 3},
                "status": "FT",
            }
        ])

    def test_home_winner_target_and_probability(self) -> None:
        rows = build_moneyline_rows([
            {
                "game_id": 101,
                "captured_at": "2026-09-12T10:00:00+00:00",
                "kickoff": "2026-09-12T12:00:00+00:00",
                "home": "Home Club",
                "away": "Away Club",
                "market": "Match Winner",
                "selection": "Home Club",
                "bookmaker_name": "Book A",
                "odds": "2.00",
            }
        ], self.result)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["target"], 1)
        self.assertEqual(rows[0]["side"], "home")
        self.assertAlmostEqual(rows[0]["implied_probability"], 0.5)

    def test_post_kickoff_observation_is_excluded(self) -> None:
        rows = build_moneyline_rows([
            {
                "game_id": 101,
                "captured_at": "2026-09-12T12:00:01+00:00",
                "kickoff": "2026-09-12T12:00:00+00:00",
                "home": "Home Club",
                "away": "Away Club",
                "market": "Match Winner",
                "selection": "Home Club",
                "odds": 2.0,
            }
        ], self.result)
        self.assertEqual(rows, [])

    def test_non_moneyline_and_unknown_selection_are_excluded(self) -> None:
        observations = [
            {
                "game_id": 101, "captured_at": "2026-09-12T10:00:00+00:00",
                "kickoff": "2026-09-12T12:00:00+00:00", "home": "Home Club",
                "away": "Away Club", "market": "Run Line", "selection": "Home Club", "odds": 2.0,
            },
            {
                "game_id": 101, "captured_at": "2026-09-12T10:00:00+00:00",
                "kickoff": "2026-09-12T12:00:00+00:00", "home": "Home Club",
                "away": "Away Club", "market": "Match Winner", "selection": "Draw", "odds": 2.0,
            },
        ]
        self.assertEqual(build_moneyline_rows(observations, self.result), [])

    def test_tied_or_unresolved_result_is_excluded(self) -> None:
        tied = _result_map([{
            "game_id": 102, "home": {"name": "A"}, "away": {"name": "B"},
            "scores": {"home": 2, "away": 2}, "status": "FT",
        }])
        self.assertEqual(tied, {})


if __name__ == "__main__":
    unittest.main()
