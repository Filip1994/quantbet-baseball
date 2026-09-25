from datetime import UTC, datetime
from types import SimpleNamespace

from quantbot.baseball.decision_lifecycle import RegisteredPick
from quantbot.baseball.fixture_evidence import FixtureObservation
from quantbot.baseball.moneyline_monitoring import monitor_due_moneyline_picks
from quantbot.baseball.monitoring_lifecycle import OddsLifecyclePolicy
from quantbot.baseball.raw_archive import ArchiveReceipt


def _pick() -> RegisteredPick:
    return RegisteredPick(
        pick_id="00000000-0000-0000-0000-000000000301",
        verification_id="00000000-0000-0000-0000-000000000302",
        final_evaluation_id="00000000-0000-0000-0000-000000000303",
        prediction_id="00000000-0000-0000-0000-000000000304",
        game_id="30",
        market_family="moneyline",
        selection="home",
        bookmaker="book-a",
        entry_observation_id="00000000-0000-0000-0000-000000000305",
        entry_odds=2.0,
        model_probability=0.55,
        market_probability=0.50,
        fair_decimal_odds=1 / 0.55,
        edge=0.05,
        expected_value_per_unit=0.10,
        uncertainty_metric=0.02,
        model_version="baseline-v1",
        feature_snapshot_ref="feature://30",
        source_data_cutoff_at="2026-09-20T17:00:00+00:00",
        kickoff_at="2026-09-20T19:00:00+00:00",
        registered_at="2026-09-20T17:02:00+00:00",
        paper_mode=True,
        state="REGISTERED",
    )


def _fixture(*, observed_at: str, status: str = "NS") -> FixtureObservation:
    return FixtureObservation(
        fixture_observation_id="00000000-0000-0000-0000-000000000310",
        game_id="30",
        provider="api-sports-baseball",
        provider_game_id=30,
        league="MLB",
        home_team_id=3001,
        home_team_name="Home Thirty",
        away_team_id=3002,
        away_team_name="Away Thirty",
        kickoff_at="2026-09-20T19:00:00+00:00",
        provider_status=status,
        observed_at=observed_at,
        source_payload_ref="s3://raw/game-30.json",
        source_payload_checksum="a" * 64,
        schema_version="1.0",
    )


def _game_row(*, status: str = "NS") -> dict:
    return {
        "id": 30,
        "date": "2026-09-20T19:00:00+00:00",
        "status": {"short": status},
        "league": {"name": "MLB"},
        "teams": {
            "home": {"id": 3001, "name": "Home Thirty"},
            "away": {"id": 3002, "name": "Away Thirty"},
        },
    }


class _Client:
    request_count = 0
    remaining_budget = 100

    def __init__(self, *, game_captured_at: str, status: str = "NS") -> None:
        self.game_captured_at = game_captured_at
        self.status = status
        self.calls: list[str] = []

    def game_with_receipt(self, game_id: int):
        assert game_id == 30
        self.calls.append("game")
        self.request_count += 1
        self.remaining_budget -= 1
        return (
            [_game_row(status=self.status)],
            ArchiveReceipt(
                ref="s3://raw/game-30-refresh.json",
                checksum="b" * 64,
                captured_at=self.game_captured_at,
            ),
        )

    def odds_with_receipt(self, game_id: int):
        assert game_id == 30
        self.calls.append("odds")
        self.request_count += 1
        self.remaining_budget -= 1
        return (
            [
                {
                    "bookmakers": [
                        {
                            "name": "book-a",
                            "bets": [
                                {
                                    "name": "Moneyline",
                                    "values": [
                                        {"value": "Home Thirty", "odd": "1.95"},
                                        {"value": "Away Thirty", "odd": "1.95"},
                                    ],
                                }
                            ],
                        }
                    ]
                }
            ],
            ArchiveReceipt(
                ref="s3://raw/game-30-odds.json",
                checksum="c" * 64,
                captured_at="2026-09-20T18:30:05+00:00",
            ),
        )


class _Repository:
    def __init__(self) -> None:
        self.pick = _pick()
        self.fixture = _fixture(observed_at="2026-09-20T18:00:00+00:00")
        self.advanced_at = None
        self.finalized_at = None
        self.observations = ()
        self.fixture_records = ()

    def unstarted_pick_ids(self, *, limit: int):
        return ()

    def due_pick_ids(self, *, as_of: datetime, limit: int):
        return (self.pick.pick_id,)

    def refresh_context(self, pick_id: str, *, as_of: datetime):
        assert pick_id == self.pick.pick_id
        return self.pick, self.fixture

    def append_fixture_observations(self, records):
        self.fixture_records = records
        self.fixture = records[0]
        return len(records)

    def append_observations(self, records):
        self.observations = records
        return len(records)

    def advance_refresh(self, pick_id: str, *, refreshed_at: datetime):
        assert pick_id == self.pick.pick_id
        self.advanced_at = refreshed_at
        return SimpleNamespace(state="MONITORING")

    def finalize_closing(self, pick_id: str, *, finalized_at: datetime):
        assert pick_id == self.pick.pick_id
        self.finalized_at = finalized_at
        return SimpleNamespace(outcome="CAPTURED")


def test_due_registered_pick_refreshes_game_before_exact_bookmaker_odds() -> None:
    client = _Client(game_captured_at="2026-09-20T18:30:00+00:00")
    repository = _Repository()

    summary = monitor_due_moneyline_picks(
        client,
        repository,
        now=datetime(2026, 9, 20, 18, 30, tzinfo=UTC),
        policy=OddsLifecyclePolicy(),
    )

    assert client.calls == ["game", "odds"]
    assert summary["fixture_calls"] == 1
    assert summary["odds_calls"] == 1
    assert summary["exact_pair_refreshes"] == 1
    assert summary["canonical_rows"] == 2
    assert len(repository.observations) == 2
    assert repository.advanced_at == datetime(2026, 9, 20, 18, 30, 5, tzinfo=UTC)


def test_due_pick_after_cutoff_finalizes_without_new_odds_call() -> None:
    client = _Client(
        game_captured_at="2026-09-20T19:00:05+00:00",
        status="IN1",
    )
    repository = _Repository()

    summary = monitor_due_moneyline_picks(
        client,
        repository,
        now=datetime(2026, 9, 20, 19, 0, tzinfo=UTC),
        policy=OddsLifecyclePolicy(),
    )

    assert client.calls == ["game"]
    assert summary["fixture_calls"] == 1
    assert summary["odds_calls"] == 0
    assert summary["finalizations"] == 1
    assert summary["closing_captured"] == 1
    assert repository.finalized_at == datetime(2026, 9, 20, 19, 0, 5, tzinfo=UTC)
