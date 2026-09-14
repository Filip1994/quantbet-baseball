from __future__ import annotations

import unittest

from quantbot.baseball.market_snapshot import build_two_way_market_snapshot


class MarketSnapshotContractTests(unittest.TestCase):
    def _row(self, **overrides: object) -> dict[str, object]:
        row: dict[str, object] = {
            "game_id": "g1",
            "captured_at": "2026-09-10T10:00:00+00:00",
            "kickoff": "2026-09-10T12:00:00+00:00",
            "market": "Moneyline",
            "home": "Home Club",
            "away": "Away Club",
            "bookmaker_name": "Book A",
            "side": "home",
            "odds": 2.0,
        }
        row.update(overrides)
        return row

    def test_requires_both_sides_from_same_bookmaker(self) -> None:
        self.assertIsNone(build_two_way_market_snapshot([self._row()]))

    def test_ignores_incomplete_bookmaker_and_uses_complete_one(self) -> None:
        rows = [
            self._row(bookmaker_name="Incomplete", side="home", odds=2.0),
            self._row(bookmaker_name="Complete", side="home", odds=2.0),
            self._row(bookmaker_name="Complete", side="away", odds=2.2),
        ]
        snapshot = build_two_way_market_snapshot(rows)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot["bookmaker_count"], 1)
        self.assertEqual(snapshot["bookmakers_used"], ["Complete"])

    def test_exact_duplicate_same_bookmaker_side_is_idempotent(self) -> None:
        rows = [
            self._row(side="home", odds=2.0),
            self._row(side="home", odds=2.0),
            self._row(side="away", odds=2.0),
        ]
        snapshot = build_two_way_market_snapshot(rows)
        self.assertIsNotNone(snapshot)

    def test_conflicting_duplicate_same_bookmaker_side_fails_closed(self) -> None:
        rows = [
            self._row(side="home", odds=2.0),
            self._row(side="home", odds=3.0),
            self._row(side="away", odds=2.0),
        ]
        self.assertIsNone(build_two_way_market_snapshot(rows))

    def test_mixed_game_ids_fail_closed(self) -> None:
        self.assertIsNone(
            build_two_way_market_snapshot(
                [
                    self._row(side="home"),
                    self._row(side="away", game_id="g2"),
                ]
            )
        )

    def test_mixed_capture_times_fail_closed(self) -> None:
        self.assertIsNone(
            build_two_way_market_snapshot(
                [
                    self._row(side="home"),
                    self._row(side="away", captured_at="2026-09-10T10:01:00+00:00"),
                ]
            )
        )

    def test_post_kickoff_snapshot_fails_closed(self) -> None:
        self.assertIsNone(
            build_two_way_market_snapshot(
                [self._row(captured_at="2026-09-10T12:00:00+00:00")]
            )
        )

    def test_naive_timestamp_fails_closed(self) -> None:
        self.assertIsNone(
            build_two_way_market_snapshot([self._row(captured_at="2026-09-10T10:00:00")])
        )

    def test_invalid_odds_fail_closed(self) -> None:
        rows = [
            self._row(side="home", odds=1.0),
            self._row(side="away", odds=2.0),
        ]
        self.assertIsNone(build_two_way_market_snapshot(rows))


if __name__ == "__main__":
    unittest.main()
