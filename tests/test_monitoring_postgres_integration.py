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
from quantbot.baseball.monitoring_lifecycle import OddsLifecyclePolicy
from quantbot.baseball.monitoring_repository import (
    PostgreSQLMoneylineMonitoringRepository,
)
from quantbot.baseball.postgres_repository import PostgreSQLEvidenceRepository
from quantbot.baseball.raw_archive import ArchiveReceipt


class _RegistrationClient:
    def odds_with_receipt(self, game_id):
        assert game_id == 20
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
                ref="s3://raw/game-20-entry.json",
                checksum="c" * 64,
                captured_at="2026-09-20T17:02:00+00:00",
            ),
        )


class _Clock:
    def __init__(self, *values):
        self.values = iter(values)

    def __call__(self):
        return next(self.values)


def _observation(
    observation_id: str,
    *,
    selection: str,
    odds: float,
    observed_at: str,
) -> OddsObservation:
    return OddsObservation(
        observation_id=observation_id,
        game_id="20",
        market_family="moneyline",
        line=None,
        selection=selection,
        bookmaker="bet365",
        decimal_odds=odds,
        raw_price=str(odds),
        observed_at=observed_at,
        retrieved_at=observed_at,
        source_payload_ref=f"s3://raw/{observation_id}.json",
        source_payload_checksum="d" * 64,
        schema_version="1.0",
        market_status="open",
        kickoff_at="2026-09-20T19:00:00+00:00",
    )


def _register_pick(connection):
    evidence = PostgreSQLEvidenceRepository(connection)
    fixture = FixtureObservation(
        fixture_observation_id=str(uuid.uuid4()),
        game_id="20",
        provider="api-sports-baseball",
        provider_game_id=20,
        league="MLB",
        home_team_id=2001,
        home_team_name="Home Twenty",
        away_team_id=2002,
        away_team_name="Away Twenty",
        kickoff_at="2026-09-20T19:00:00+00:00",
        provider_status="NS",
        observed_at="2026-09-20T17:00:00+00:00",
        source_payload_ref="s3://raw/games-20.json",
        source_payload_checksum="e" * 64,
        schema_version="1.0",
    )
    assert evidence.append_fixture_observations((fixture,)) == 1

    repository = PostgreSQLMoneylineDecisionRepository(connection)
    opening_home = _observation(
        "00000000-0000-0000-0000-000000000201",
        selection="home",
        odds=2.10,
        observed_at="2026-09-20T17:00:00+00:00",
    )
    opening_away = _observation(
        "00000000-0000-0000-0000-000000000202",
        selection="away",
        odds=1.80,
        observed_at="2026-09-20T17:00:00+00:00",
    )
    assert repository.append_observations((opening_home, opening_away)) == 2

    prediction = build_model_prediction(
        game_id="20",
        model_version="baseline-v1",
        feature_snapshot_ref="feature://20/1659",
        source_data_cutoff_at="2026-09-20T16:59:00+00:00",
        predicted_at="2026-09-20T17:00:30+00:00",
        home_probability=0.55,
        away_probability=0.45,
        uncertainty_metric=0.02,
    )
    preliminary = evaluate_preliminary_moneyline(
        repository,
        prediction,
        bookmaker="bet365",
        evaluated_at=datetime(2026, 9, 20, 17, 1, tzinfo=UTC),
        policy=MoneylineDecisionPolicy(),
    )
    assert preliminary is not None
    assert preliminary.candidate is not None

    registered = verify_and_register_moneyline(
        _RegistrationClient(),
        repository,
        preliminary.candidate.evaluation_id,
        clock=_Clock(
            datetime(2026, 9, 20, 17, 1, 30, tzinfo=UTC),
            datetime(2026, 9, 20, 17, 2, 5, tzinfo=UTC),
            datetime(2026, 9, 20, 17, 2, 6, tzinfo=UTC),
            datetime(2026, 9, 20, 17, 2, 7, tzinfo=UTC),
        ),
        policy=MoneylineDecisionPolicy(),
    )
    assert registered.pick is not None
    return registered.pick


def test_registered_pick_monitoring_finalizes_exact_closing_pair() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    apply_migrations(Path("."), database_url)

    with psycopg.connect(database_url) as connection:
        pick = _register_pick(connection)
        monitoring = PostgreSQLMoneylineMonitoringRepository(connection)
        policy = OddsLifecyclePolicy(
            monitoring_interval_seconds=900,
            current_max_age_seconds=1800,
            closing_max_age_seconds=1200,
        )

        state = monitoring.start_monitoring(
            pick.pick_id,
            started_at=datetime(2026, 9, 20, 17, 3, tzinfo=UTC),
            policy=policy,
        )
        assert state.state == "MONITORING"
        assert (
            monitoring.start_monitoring(
                pick.pick_id,
                started_at=datetime(2026, 9, 20, 17, 4, tzinfo=UTC),
                policy=policy,
            )
            == state
        )

        close_home = _observation(
            "00000000-0000-0000-0000-000000000203",
            selection="home",
            odds=1.85,
            observed_at="2026-09-20T18:50:00+00:00",
        )
        close_away = _observation(
            "00000000-0000-0000-0000-000000000204",
            selection="away",
            odds=2.05,
            observed_at="2026-09-20T18:50:00+00:00",
        )
        assert monitoring.append_observations((close_home, close_away)) == 2

        finalization = monitoring.finalize_closing(
            pick.pick_id,
            finalized_at=datetime(2026, 9, 20, 19, 0, 1, tzinfo=UTC),
        )
        assert finalization.outcome == "CAPTURED"
        assert finalization.closing_observation_id == close_home.observation_id
        assert (
            monitoring.finalize_closing(
                pick.pick_id,
                finalized_at=datetime(2026, 9, 20, 19, 1, tzinfo=UTC),
            )
            == finalization
        )

        lifecycle = monitoring.read_lifecycle(
            pick.pick_id,
            as_of=datetime(2026, 9, 20, 19, 0, 2, tzinfo=UTC),
        )
        assert lifecycle.state == "CLOSED_FOR_ODDS"
        assert lifecycle.opening is not None
        assert lifecycle.opening.decimal_odds == 2.10
        assert lifecycle.entry.decimal_odds == 2.00
        assert lifecycle.current is not None
        assert lifecycle.current.decimal_odds == 1.85
        assert lifecycle.current.freshness == "FRESH"
        assert lifecycle.closing is not None
        assert lifecycle.closing.decimal_odds == 1.85
        assert lifecycle.closing_outcome == "CAPTURED"
        assert lifecycle.markers[close_home.observation_id] == ("CURRENT", "CLOSE")

        closed_state = monitoring.monitoring_state(pick.pick_id)
        assert closed_state is not None
        assert closed_state.state == "CLOSED_FOR_ODDS"
        assert closed_state.next_refresh_at is None

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT transition_type FROM pick_monitoring_transitions "
                "WHERE pick_id = %s ORDER BY occurred_at",
                (pick.pick_id,),
            )
            assert [row[0] for row in cursor.fetchall()] == [
                "MONITORING_STARTED",
                "ODDS_CLOSED",
            ]
