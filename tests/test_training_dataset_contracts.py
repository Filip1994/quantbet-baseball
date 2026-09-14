from __future__ import annotations

import unittest

from quantbot.baseball.training_dataset import _result_map, build_moneyline_rows


class TrainingDatasetContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.completed = _result_map(
            [
                {
                    "game_id": 200,
                    "home": {"name": "Home Club"},
                    "away": {"name": "Away Club"},
                    "scores": {"home": 2, "away": 4},
                    "status": "FT",
                }
            ]
        )

    def _observation(self, **overrides: object) -> dict[str, object]:
        observation: dict[str, object] = {
            "game_id": 200,
            "captured_at": "2026-09-10T10:00:00+00:00",
            "kickoff": "2026-09-10T12:00:00+00:00",
            "home": "Home Club",
            "away": "Away Club",
            "market": "Match Winner",
            "selection": "Away Club",
            "odds": 2.0,
        }
        observation.update(overrides)
        return observation

    def test_away_selection_receives_winning_target(self) -> None:
        rows = build_moneyline_rows([self._observation()], self.completed)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["side"], "away")
        self.assertEqual(rows[0]["target"], 1)

    def test_non_finite_or_non_positive_margin_odds_are_rejected(self) -> None:
        observations = [
            self._observation(odds=1.0),
            self._observation(odds=0),
            self._observation(odds="not-a-number"),
        ]
        self.assertEqual(build_moneyline_rows(observations, self.completed), [])

    def test_postponed_result_is_not_a_training_label(self) -> None:
        postponed = _result_map(
            [
                {
                    "game_id": 201,
                    "home": {"name": "Home Club"},
                    "away": {"name": "Away Club"},
                    "scores": {"home": None, "away": None},
                    "status": "Postponed",
                }
            ]
        )
        self.assertEqual(postponed, {})

    def test_identical_game_snapshot_side_is_deduplicated(self) -> None:
        observation = self._observation()
        rows = build_moneyline_rows([observation, dict(observation)], self.completed)
        self.assertEqual(len(rows), 1)

    def test_observation_exactly_at_kickoff_is_excluded(self) -> None:
        rows = build_moneyline_rows(
            [
                self._observation(
                    captured_at="2026-09-10T12:00:00+00:00",
                    kickoff="2026-09-10T12:00:00+00:00",
                )
            ],
            self.completed,
        )
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
