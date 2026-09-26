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
        self.poll_attempts = []

    def latest_odds_poll_times(self):
        return {
            record.game_id: datetime.fromisoformat(record.attempted_at)
            for record in self.poll_attempts
        }

    def append_observations(self, records):
        self.records.extend(records)
        return len(records)

    def append_fixture_observations(self, records):
        self.fixtures.extend(records)
        return len(records)

    def append_odds_poll_attempt(self, record):
        if any(
            existing.poll_attempt_id == record.poll_attempt_id
            for existing in self.poll_attempts
        ):
            return False
        self.poll_attempts.append(record)
        return True


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
    assert result["due_events"] == 1
    assert result["not_due_events"] == 0
    assert result["games_selected"] == 1
    assert result["due_events_unselected"] == 0
    assert result["odds_calls"] == 1
    assert result["canonical_rows"] == 2
    assert result["observations_inserted"] == 2
    assert result["poll_attempts_inserted"] == 1
    assert len(repository.poll_attempts) == 1
    assert repository.poll_attempts[0].response_rows == 1
    assert {record.selection for record in repository.records} == {"home", "away"}
    assert all(record.game_id == "10" for record in repository.records)
    assert {record.game_id for record in repository.fixtures} == {"10", "11"}
    assert {record.home_team_id for record in repository.fixtures} == {101, 303}
    assert "schema_market_names_json" not in result
    assert "schema_candidate_values_json" not in result


class RecentlyObservedRepository(FakeRepository):
    def latest_odds_poll_times(self):
        return {"10": datetime(2030, 9, 18, 16, 50, tzinfo=UTC)}


def test_skips_pregame_game_when_adaptive_scheduler_says_not_due() -> None:
    now = datetime(2030, 9, 18, 17, 0, tzinfo=UTC)
    client = FakeClient()
    repository = RecentlyObservedRepository()

    result = collect_with_dependencies(
        client,
        repository,
        now=now,
        max_odds_requests=10,
        clock=lambda: now,
    )

    assert result["pregame_games"] == 1
    assert result["due_events"] == 0
    assert result["not_due_events"] == 1
    assert result["games_selected"] == 0
    assert result["due_events_unselected"] == 0
    assert result["odds_calls"] == 0
    assert result["canonical_rows"] == 0
    assert result["observations_inserted"] == 0
    assert client.request_count == 2


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
    assert result["schema_odds_payload_rows"] == 1
    assert result["schema_empty_odds_calls"] == 0
    assert result["schema_nonempty_odds_calls"] == 1
    assert result["schema_bookmaker_records"] == 1
    assert json.loads(result["schema_top_level_keys_json"]) == ["bookmakers"]
    assert json.loads(result["schema_response_shapes_json"]) == ["bookmakers"]
    assert "1.90" not in result["schema_candidate_values_json"]
    assert "2.10" not in result["schema_candidate_values_json"]


class EmptyOddsClient(FakeClient):
    def odds_with_receipt(self, game_id):
        self.request_count += 1
        assert game_id == 10
        return (
            [],
            ArchiveReceipt(
                ref="s3://raw/game-10-empty.json",
                checksum="c" * 64,
                captured_at="2030-09-18T17:00:00+00:00",
            ),
        )


def test_canary_schema_probe_distinguishes_empty_odds_response() -> None:
    now = datetime(2030, 9, 18, 17, 0, tzinfo=UTC)
    client = EmptyOddsClient()
    repository = FakeRepository()

    result = collect_with_dependencies(
        client,
        repository,
        now=now,
        max_odds_requests=10,
        clock=lambda: now,
        schema_probe=True,
    )

    assert result["odds_calls"] == 1
    assert result["schema_odds_payload_rows"] == 0
    assert result["schema_empty_odds_calls"] == 1
    assert result["schema_nonempty_odds_calls"] == 0
    assert result["schema_bookmaker_records"] == 0
    assert json.loads(result["schema_top_level_keys_json"]) == []
    assert json.loads(result["schema_response_shapes_json"]) == []
    assert json.loads(result["schema_market_names_json"]) == []
    assert json.loads(result["schema_candidate_values_json"]) == {}
    assert result["poll_attempts_inserted"] == 1
    assert len(repository.poll_attempts) == 1
    attempt = repository.poll_attempts[0]
    assert attempt.response_rows == 0
    assert attempt.raw_market_rows == 0
    assert attempt.canonical_rows == 0
    assert attempt.source_payload_ref == "s3://raw/game-10-empty.json"

    follow_up = collect_with_dependencies(
        EmptyOddsClient(),
        repository,
        now=datetime(2030, 9, 18, 17, 5, tzinfo=UTC),
        max_odds_requests=10,
        clock=lambda: datetime(2030, 9, 18, 17, 5, tzinfo=UTC),
    )
    assert follow_up["due_events"] == 0
    assert follow_up["games_selected"] == 0
    assert follow_up["odds_calls"] == 0
    assert follow_up["poll_attempts_inserted"] == 0


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
