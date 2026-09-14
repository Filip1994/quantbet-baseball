from __future__ import annotations

import unittest

from quantbot.baseball.training_dataset import _is_moneyline, build_moneyline_rows


class MarketContractTests(unittest.TestCase):
    def test_accepts_explicit_full_game_winner_markets(self) -> None:
        for market in ("Moneyline", "Match Winner", "Game Winner", "Match Result", "Game Result"):
            self.assertTrue(_is_moneyline(market))

    def test_rejects_ambiguous_or_non_moneyline_markets(self) -> None:
        for market in (
            "Winner - First Five Innings",
            "Player to Win",
            "Run Line",
            "Game Total",
            "Series Winner",
            "Winner + Run Line",
        ):
            self.assertFalse(_is_moneyline(market))

    def test_market_contract_is_applied_before_row_creation(self) -> None:
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
            "captured_at": "2026-09-10T10:00:00+00:00",
            "kickoff": "2026-09-10T12:00:00+00:00",
            "home": "Home Club",
            "away": "Away Club",
            "market": "Winner - First Five Innings",
            "selection": "Away Club",
            "odds": 2.0,
        }
        self.assertEqual(build_moneyline_rows([observation], result), [])
