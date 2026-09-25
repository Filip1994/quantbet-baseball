from datetime import UTC, datetime
from types import SimpleNamespace

from quantbot.baseball.fixture_evidence import FixtureObservation
from quantbot.baseball.moneyline_settlement import settle_due_moneyline_picks
from quantbot.baseball.raw_archive import ArchiveReceipt


class _Client:
    def __init__(self, status: str) -> None:
        self.status = status
        self.request_count = 0
        self.remaining_budget = 100

    def game_with_receipt(self, game_id: int):
        assert game_id == 30
        self.request_count += 1
        return (
            [
                {
                    "id": 30,
                    "date": "2026-09-20T19:00:00+00:00",
                    "league": {"name": "MLB"},
                    "teams": {
                        "home": {"id": 3001, "name": "Home Thirty"},
                        "away": {"id": 3002, "name": "Away Thirty"},
                    },
                    "status": {"short": self.status},
                    "scores": {
                        "home": {"total": 5},
                        "away": {"total": 3},
                    },
                }
            ],
            ArchiveReceipt(
                ref="s3://raw/game-30-final.json",
                checksum="c" * 64,
                captured_at="2026-09-20T22:00:00+00:00",
            ),
        )


class _Repository:
    def __init__(self) -> None:
        self.results = []
        self.settled = []

    def due_pick_ids(self, *, as_of, limit):
        assert limit == 10
        return ("pick-30",)

    def refresh_context(self, pick_id, *, as_of):
        assert pick_id == "pick-30"
        return (
            SimpleNamespace(pick_id="pick-30"),
            FixtureObservation(
                fixture_observation_id="fixture-30-pregame",
                game_id="30",
                provider="api-sports-baseball",
                provider_game_id=30,
                league="MLB",
                home_team_id=3001,
                home_team_name="Home Thirty",
                away_team_id=3002,
                away_team_name="Away Thirty",
                kickoff_at="2026-09-20T19:00:00+00:00",
                provider_status="NS",
                observed_at="2026-09-20T18:00:00+00:00",
                source_payload_ref="s3://raw/game-30-pregame.json",
                source_payload_checksum="d" * 64,
                schema_version="1.0",
            ),
        )

    def append_fixture_observations(self, records):
        assert len(records) == 1
        return 1

    def append_result(self, result):
        self.results.append(result)
        return True

    def settle(self, pick_id, result, *, settled_at):
        self.settled.append((pick_id, result, settled_at))
        return SimpleNamespace(outcome="WIN", clv_status="AVAILABLE")


def test_terminal_game_creates_result_and_settlement() -> None:
    repository = _Repository()
    summary = settle_due_moneyline_picks(
        _Client("FT"),
        repository,
        now=datetime(2026, 9, 20, 22, 0, 1, tzinfo=UTC),
    )

    assert summary["game_calls"] == 1
    assert summary["result_facts_inserted"] == 1
    assert summary["settlements"] == 1
    assert summary["wins"] == 1
    assert summary["clv_available"] == 1
    assert len(repository.results) == 1
    assert len(repository.settled) == 1


def test_nonterminal_game_is_not_settled() -> None:
    repository = _Repository()
    summary = settle_due_moneyline_picks(
        _Client("IN1"),
        repository,
        now=datetime(2026, 9, 20, 19, 30, tzinfo=UTC),
    )

    assert summary["nonterminal"] == 1
    assert summary["settlements"] == 0
    assert repository.results == []
    assert repository.settled == []
