import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from quantbot.baseball.db import apply_migrations
from quantbot.baseball.decision_lifecycle import build_model_prediction
from quantbot.baseball.decision_repository import PostgreSQLMoneylineDecisionRepository
from quantbot.baseball.evidence import OddsObservation
from quantbot.baseball.fixture_evidence import FixtureObservation
from quantbot.baseball.moneyline_registration import (
    MoneylineDecisionPolicy,
    evaluate_preliminary_moneyline,
    verify_and_register_moneyline,
)
from quantbot.baseball.postgres_repository import PostgreSQLEvidenceRepository
from quantbot.baseball.raw_archive import ArchiveReceipt
from quantbot.baseball.runtime_evidence import CollectionCycle


def _observation() -> OddsObservation:
    return OddsObservation(
        observation_id=str(uuid.uuid4()),
        game_id="1",
        market_family="moneyline",
        line=None,
        selection="home",
        bookmaker="book-a",
        decimal_odds=2.1,
        raw_price="2.1",
        observed_at="2026-09-20T17:00:00+00:00",
        retrieved_at="2026-09-20T17:00:00+00:00",
        source_payload_ref="s3://raw/payload.json",
        source_payload_checksum="a" * 64,
        schema_version="1.0",
        market_status="open",
        kickoff_at="2026-09-20T19:00:00+00:00",
    )


def test_migrations_and_repository_are_idempotent() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    apply_migrations(Path("."), database_url)
    record = _observation()

    with psycopg.connect(database_url) as connection:
        repository = PostgreSQLEvidenceRepository(connection)
        assert repository.append_observation(record) is True
        assert repository.append_observation(record) is False
        assert repository.get_observation(record.observation_id) == record
        assert repository.stats().observations == 1
        assert (
            repository.latest_observation_times()["1"]
            .isoformat()
            .startswith("2026-09-20T17:00:00")
        )

        fixture = FixtureObservation(
            fixture_observation_id=str(uuid.uuid4()),
            game_id="1",
            provider="api-sports-baseball",
            provider_game_id=1,
            league="MLB",
            home_team_id=101,
            home_team_name="Home Club",
            away_team_id=202,
            away_team_name="Away Club",
            kickoff_at="2026-09-20T19:00:00+00:00",
            provider_status="NS",
            observed_at="2026-09-20T17:00:00+00:00",
            source_payload_ref="s3://raw/games.json",
            source_payload_checksum="b" * 64,
            schema_version="1.0",
        )
        assert repository.append_fixture_observations((fixture,)) == 1
        assert repository.append_fixture_observations((fixture,)) == 0

        started = datetime(2026, 9, 20, 17, 0, tzinfo=UTC)
        cycle = CollectionCycle.from_summary(
            cycle_id=str(uuid.uuid4()),
            started_at=started,
            finished_at=started,
            summary={
                "status": "collected",
                "games_seen": 1,
                "fixture_observations_inserted": 1,
                "pregame_games": 1,
                "due_events": 1,
                "games_selected": 1,
                "odds_calls": 1,
                "raw_market_rows": 2,
                "canonical_rows": 1,
                "observations_inserted": 1,
                "api_requests": 3,
                "api_remaining": 75,
                "errors": 0,
            },
        )
        assert repository.append_collection_cycle(cycle) is True
        assert repository.append_collection_cycle(cycle) is False

        repository.append_runtime_cycle(
            run_id=str(uuid.uuid4()),
            started_at=started,
            finished_at=started,
            collection_enabled=False,
            mode="storage-ready",
            status="ready",
            stats={},
        )

        health = repository.health_snapshot()
        assert health["fixture_observations"] == 1
        assert health["distinct_fixtures"] == 1
        assert health["odds_observations"] == 1
        assert health["distinct_quote_games"] == 1
        assert health["bookmakers"] == 1
        assert health["pick_events"] == 0
        assert health["collection_cycles"] == 1
        assert health["runtime_cycles"] == 1


class _FreshQuoteClient:
    def odds_with_receipt(self, game_id):
        assert game_id == 2
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
                                        {"value": "Home", "odd": "2.00"},
                                        {"value": "Away", "odd": "1.90"},
                                    ],
                                }
                            ],
                        }
                    ]
                }
            ],
            ArchiveReceipt(
                ref="s3://raw/game-2-final.json",
                checksum="c" * 64,
                captured_at="2026-09-20T17:02:00+00:00",
            ),
        )


class _Clock:
    def __init__(self, *values):
        self._values = iter(values)

    def __call__(self):
        return next(self._values)


def _moneyline_observation(
    *,
    observation_id,
    selection,
    odds,
):
    return OddsObservation(
        observation_id=observation_id,
        game_id="2",
        market_family="moneyline",
        line=None,
        selection=selection,
        bookmaker="book-a",
        decimal_odds=odds,
        raw_price=str(odds),
        observed_at="2026-09-20T17:00:00+00:00",
        retrieved_at="2026-09-20T17:00:00+00:00",
        source_payload_ref="s3://raw/game-2-opening.json",
        source_payload_checksum="d" * 64,
        schema_version="1.0",
        market_status="open",
        kickoff_at="2026-09-20T19:00:00+00:00",
    )


def test_moneyline_candidate_requires_fresh_quote_before_registration() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    apply_migrations(Path("."), database_url)

    fixture = FixtureObservation(
        fixture_observation_id=str(uuid.uuid4()),
        game_id="2",
        provider="api-sports-baseball",
        provider_game_id=2,
        league="MLB",
        home_team_id=301,
        home_team_name="Home Two",
        away_team_id=302,
        away_team_name="Away Two",
        kickoff_at="2026-09-20T19:00:00+00:00",
        provider_status="NS",
        observed_at="2026-09-20T17:00:00+00:00",
        source_payload_ref="s3://raw/games-2.json",
        source_payload_checksum="e" * 64,
        schema_version="1.0",
    )
    home = _moneyline_observation(
        observation_id="00000000-0000-0000-0000-000000000021",
        selection="home",
        odds=2.10,
    )
    away = _moneyline_observation(
        observation_id="00000000-0000-0000-0000-000000000022",
        selection="away",
        odds=1.80,
    )
    prediction = build_model_prediction(
        game_id="2",
        model_version="baseline-v1",
        feature_snapshot_ref="feature://2/1659",
        source_data_cutoff_at="2026-09-20T16:59:00+00:00",
        predicted_at="2026-09-20T17:00:30+00:00",
        home_probability=0.55,
        away_probability=0.45,
        uncertainty_metric=0.02,
    )
    policy = MoneylineDecisionPolicy()

    with psycopg.connect(database_url) as connection:
        evidence = PostgreSQLEvidenceRepository(connection)
        assert evidence.append_fixture_observations((fixture,)) == 1

        repository = PostgreSQLMoneylineDecisionRepository(connection)
        assert repository.append_observations((home, away)) == 2

        preliminary = evaluate_preliminary_moneyline(
            repository,
            prediction,
            bookmaker="book-a",
            evaluated_at=datetime(2026, 9, 20, 17, 1, tzinfo=UTC),
            policy=policy,
        )
        assert preliminary is not None
        assert preliminary.candidate is not None
        assert preliminary.candidate.selection == "home"

        clock = _Clock(
            datetime(2026, 9, 20, 17, 1, 30, tzinfo=UTC),
            datetime(2026, 9, 20, 17, 2, 5, tzinfo=UTC),
            datetime(2026, 9, 20, 17, 2, 6, tzinfo=UTC),
            datetime(2026, 9, 20, 17, 2, 7, tzinfo=UTC),
        )
        registered = verify_and_register_moneyline(
            _FreshQuoteClient(),
            repository,
            preliminary.candidate.evaluation_id,
            clock=clock,
            policy=policy,
        )

        assert registered.verification.status == "READY"
        assert registered.final_evaluation is not None
        assert registered.final_evaluation.stage == "FINAL"
        assert registered.pick is not None
        assert registered.pick.selection == "home"
        assert registered.pick.entry_odds == 2.00
        assert registered.pick.paper_mode is True
        assert registered.pick.state == "REGISTERED"

        replay = verify_and_register_moneyline(
            _FreshQuoteClient(),
            repository,
            preliminary.candidate.evaluation_id,
            clock=_Clock(
                datetime(2026, 9, 20, 17, 3, tzinfo=UTC),
                datetime(2026, 9, 20, 17, 3, 1, tzinfo=UTC),
            ),
            policy=policy,
        )
        assert replay.pick == registered.pick
        assert replay.verification == registered.verification
