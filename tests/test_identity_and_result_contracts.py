from __future__ import annotations

import unittest

from quantbot.baseball.training_dataset import _result_map, build_moneyline_rows


class IdentityAndResultContractTests(unittest.TestCase):
    def test_team_matching_ignores_case_spacing_and_punctuation(self) -> None:
        results = _result_map(
            [
                {
                    "game_id": 301,
                    "home": {"name": "New York Yankees"},
                    "away": {"name": "Boston Red Sox"},
                    "scores": {"home": 5, "away": 2},
                    "status": "FT",
                }
            ]
        )
        observation = {
            "game_id": 301,
            "captured_at": "2026-09-10T10:00:00+00:00",
            "kickoff": "2026-09-10T12:00:00+00:00",
            "home": "New York Yankees",
            "away": "Boston Red Sox",
            "market": "Moneyline",
            "selection": " boston-red_sox ",
            "odds": 2.4,
        }
        rows = build_moneyline_rows([observation], results)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["side"], "away")
        self.assertEqual(rows[0]["target"], 0)

    def test_conflicting_duplicate_results_fail_closed(self) -> None:
        results = _result_map(
            [
                {
                    "game_id": 302,
                    "home": {"name": "Home Club"},
                    "away": {"name": "Away Club"},
                    "scores": {"home": 4, "away": 2},
                    "status": "FT",
                },
                {
                    "game_id": 302,
                    "home": {"name": "Home Club"},
                    "away": {"name": "Away Club"},
                    "scores": {"home": 3, "away": 5},
                    "status": "FT",
                },
            ]
        )
        self.assertNotIn("302", results)

    def test_identical_duplicate_results_are_idempotent(self) -> None:
        game = {
            "game_id": 303,
            "home": {"name": "Home Club"},
            "away": {"name": "Away Club"},
            "scores": {"home": 4, "away": 2},
            "status": "FT",
        }
        self.assertEqual(_result_map([game, dict(game)]), _result_map([game]))
