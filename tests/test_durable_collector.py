import json
from datetime import UTC, datetime

from quantbot.baseball.durable_collector import (
    collect_with_dependencies,
    remaining_broad_odds_capacity,
)
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
                        "home": {"id": 101, "name": "Home Club"},
                        "away": {"id": 202, "name": "Away Club"},
                    },
                    "league": {"name": "MLB"},
                    "status": {"short": "NS"},
                },
                {
                    "id": 11,
                    "date": "2030-09-18T16:00:00+00:00",
                    "teams": {
                        "home": {"id": 303, "name": "Started Home"},
                        "away": {"id": 404, "name": "Started Away"},
                    },
                    "league": {"name": "MLB"},
                    "status": {"short": "FT"},
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
    assert result["fixture_observations_inserted"] == 2
    assert result["pregame_games"] == 1
    assert result["games_selected"] == 1
    assert result["odds_calls"] == 1
    assert result["canonical_rows"] == 2
    assert result["observations_inserted"] == 2
    assert {record.selection for record in repository.records} == {"home", "away"}
    assert all(record.game_id == "10" for record in repository.records)
    assert {record.game_id for record in repository.fixtures} == {"10", "11"}
    assert {record.home_team_id for record in repository.fixtures} == {101, 303}
    assert "schema_market_names_json" not in result
    assert "schema_candidate_values_json" not in result


def test_canary_schema_probe_reports_market_names_without_prices() -> None:
    now = datetime(2030, 9, 18, 17, 0, tzinfo=UTC)
    client = FakeClient()
    repository = FakeRepository()

    result = collect_with_dependencies(
        client,
        repository,
        now=now,
        max_odds_requests=10,
        clock=lambda: now,
        schema_probe=True,
    )

    market_names = json.loads(result["schema_market_names_json"])
    candidates = json.loads(result["schema_candidate_values_json"])

    assert market_names == ["Moneyline"]
    assert candidates == {"Moneyline": ["Away", "Home"]}
    assert "1.90" not in result["schema_candidate_values_json"]
    assert "2.10" not in result["schema_candidate_values_json"]


def test_shared_cycle_budget_reduces_broad_odds_capacity() -> None:
    assert (
        remaining_broad_odds_capacity(
            cycle_request_cap=75,
            requests_used=0,
            max_odds_requests=76,
        )
        == 73
    )
    assert (
        remaining_broad_odds_capacity(
            cycle_request_cap=75,
            requests_used=30,
            max_odds_requests=76,
        )
        == 43
    )
    assert (
        remaining_broad_odds_capacity(
            cycle_request_cap=75,
            requests_used=74,
            max_odds_requests=76,
        )
        == 0
    )
