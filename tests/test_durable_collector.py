from datetime import UTC, datetime

from quantbot.baseball.durable_collector import collect_with_dependencies
from quantbot.baseball.raw_archive import ArchiveReceipt


class FakeRepository:
    def __init__(self) -> None:
        self.records = []
        self.fixtures = []

    def latest_observation_times(self):
        return {}

    def append_observations(self, records):
        self.records.extend(records)
        return len(records)

    def append_fixture_observations(self, records):
        self.fixtures.extend(records)
        return len(records)


class FakeClient:
    request_count = 0
    remaining_budget = 78

    def games_by_date_with_receipt(self, date_iso):
        self.request_count += 1
        response = []
        if date_iso == "2030-09-18":
            response = [
                {
                    "id": 10,
                "date": "2030-09-18T19:00:00+00:00",
                "teams": {
                    "home": {"name": "Home Club"},
                    "away": {"name": "Away Club"},
                },
                "league": {"name": "MLB"},
                },
                {
                    "id": 11,
                "date": "2030-09-18T16:00:00+00:00",
                "teams": {
                    "home": {"name": "Started Home"},
                    "away": {"name": "Started Away"},
                },
                "league": {"name": "MLB"},
                },
            ]
        return (
            response,
            ArchiveReceipt(
                ref=f"s3://raw/games-{date_iso}.json",
                checksum="b" * 64,
                captured_at="2030-09-18T17:00:00+00:00",
            ),
        )

    def odds_with_receipt(self, game_id):
        self.request_count += 1
        assert game_id == 10
        return (
            [
                {
                    "bookmakers": [
                        {
                            "name": "bet365",
                            "bets": [
                                {
                                    "name": "Moneyline",
                                    "values": [
                                        {"value": "Home", "odd": "1.90"},
                                        {"value": "Away", "odd": "2.10"},
                                    ],
                                }
                            ],
                        }
                    ]
                }
            ],
            ArchiveReceipt(
                ref="s3://raw/game-10.json",
                checksum="a" * 64,
                captured_at="2030-09-18T17:00:00+00:00",
            ),
        )


def test_collects_only_strict_pregame_games_into_repository() -> None:
    now = datetime(2030, 9, 18, 17, 0, tzinfo=UTC)
    client = FakeClient()
    repository = FakeRepository()

    result = collect_with_dependencies(
        client,
        repository,
        now=now,
        max_odds_requests=10,
        clock=lambda: now,
    )

    assert result["games_seen"] == 2
    assert result["fixture_observations"] == 2
    assert result["fixtures_inserted"] == 2
    assert result["pregame_games"] == 1
    assert result["games_selected"] == 1
    assert result["odds_calls"] == 1
    assert result["canonical_rows"] == 2
    assert result["observations_inserted"] == 2
    assert {record.selection for record in repository.records} == {"home", "away"}
    assert all(record.game_id == "10" for record in repository.records)
    assert {record.game_id for record in repository.fixtures} == {"10", "11"}
