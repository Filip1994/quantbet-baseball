from __future__ import annotations

import unittest

from quantbot.baseball.training_dataset import _parse_time, build_moneyline_rows


class TimestampContractTests(unittest.TestCase):
    def test_parse_time_normalizes_z_suffix_to_utc_aware_datetime(self) -> None:
        parsed = _parse_time("2026-09-10T12:00:00Z")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertIsNotNone(parsed.tzinfo)
        self.assertEqual(parsed.utcoffset().total_seconds(), 0)

    def test_naive_observation_timestamps_are_rejected(self) -> None:
        result = {
            "200": {
                "home": "Home Club",
                "away": "Away Club",
                "home_score": 2,
                "away_score": 4,
                "status": "ft",
            }
        }
        observation = {
            "game_id": 200,
            "captured_at": "2026-09-10T10:00:00",
            "kickoff": "2026-09-10T12:00:00",
            "home": "Home Club",
            "away": "Away Club",
            "market": "Match Winner",
            "selection": "Away Club",
            "odds": 2.0,
        }
        self.assertEqual(build_moneyline_rows([observation], result), [])

    def test_malformed_timestamp_is_rejected(self) -> None:
        result = {
            "200": {
                "home": "Home Club",
                "away": "Away Club",
                "home_score": 2,
                "away_score": 4,
                "status": "ft",
            }
        }
        observation = {
            "game_id": 200,
            "captured_at": "not-a-timestamp",
            "kickoff": "2026-09-10T12:00:00+00:00",
            "home": "Home Club",
            "away": "Away Club",
            "market": "Match Winner",
            "selection": "Away Club",
            "odds": 2.0,
        }
        self.assertEqual(build_moneyline_rows([observation], result), [])
