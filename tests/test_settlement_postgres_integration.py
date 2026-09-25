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
from quantbot.baseball.fixture_evidence import (
    FixtureObservation,
    canonical_fixture_observation,
)
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
from quantbot.baseball.settlement_lifecycle import build_game_result_fact
from quantbot.baseball.settlement_repository import (
    PostgreSQLMoneylineSettlementRepository,
)


class _RegistrationClient:
    def odds_with_receipt(self, game_id):
        assert game_id == 40
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
                ref="s3://raw/game-40-entry.json",
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
        game_id="40",
        market_family="moneyline",
        line=None,
        selection=selection,
        bookmaker="book-a",
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
        game_id="40",
        provider="api-sports-baseball",
        provider_game_id=40,
        league="MLB",
        home_team_id=4001,
        home_team_name="Home Forty",
        away_team_id=4002,
        away_team_name="Away Forty",
        kickoff_at="2026-09-20T19:00:00+00:00",
        provider_status="NS",
        observed_at="2026-09-20T17:00:00+00:00",
        source_payload_ref="s3://raw/games-40.json",
        source_payload_checksum="e" * 64,
        schema_version="1.0",
    )
    assert evidence.append_fixture_observations((fixture,)) == 1

    repository = PostgreSQLMoneylineDecisionRepository(connection)
    opening_home = _observation(
        "00000000-0000-0000-0000-000000000401",
        selection="home",
        odds=2.10,
        observed_at="2026-09-20T17:00:00+00:00",
    )
    opening_away = _observation(
        "00000000-0000-0000-0000-000000000402",
        selection="away",
        odds=1.80,
        observed_at="2026-09-20T17:00:00+00:00",
    )
    assert repository.append_observations((opening_home, opening_away)) == 2

    prediction = build_model_prediction(
        game_id="40",
        model_version="baseline-v1",
        feature_snapshot_ref="feature://40/1659",
        source_data_cutoff_at="2026-09-20T16:59:00+00:00",
        predicted_at="2026-09-20T17:00:30+00:00",
        home_probability=0.55,
        away_probability=0.45,
        uncertainty_metric=0.02,
    )
    preliminary = evaluate_preliminary_moneyline(
        repository,
        prediction,
        bookmaker="book-a",
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


def test_registered_pick_settles_from_authoritative_result_with_clv() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    apply_migrations(Path("."), database_url)

    with psycopg.connect(database_url) as connection:
        pick = _register_pick(connection)
        monitoring = PostgreSQLMoneylineMonitoringRepository(connection)
        monitoring.start_monitoring(
            pick.pick_id,
            started_at=datetime(2026, 9, 20, 17, 3, tzinfo=UTC),
            policy=OddsLifecyclePolicy(),
        )

        close_home = _observation(
            "00000000-0000-0000-0000-000000000403",
            selection="home",
            odds=1.85,
            observed_at="2026-09-20T18:50:00+00:00",
        )
        close_away = _observation(
            "00000000-0000-0000-0000-000000000404",
            selection="away",
            odds=2.05,
            observed_at="2026-09-20T18:50:00+00:00",
        )
        assert monitoring.append_observations((close_home, close_away)) == 2
        closing = monitoring.finalize_closing(
            pick.pick_id,
            finalized_at=datetime(2026, 9, 20, 19, 0, 1, tzinfo=UTC),
        )
        assert closing.outcome == "CAPTURED"

        settlement_repository = PostgreSQLMoneylineSettlementRepository(connection)
        before_dashboard = settlement_repository.dashboard_snapshot()
        before_health = PostgreSQLEvidenceRepository(connection).health_snapshot()

        receipt = ArchiveReceipt(
            ref="s3://raw/game-40-final.json",
            checksum="f" * 64,
            captured_at="2026-09-20T22:00:00+00:00",
        )
        game = {
            "id": 40,
            "date": "2026-09-20T19:00:00+00:00",
            "league": {"name": "MLB"},
            "teams": {
                "home": {"id": 4001, "name": "Home Forty"},
                "away": {"id": 4002, "name": "Away Forty"},
            },
            "status": {"short": "FT", "long": "Finished"},
            "scores": {
                "home": {"total": 5},
                "away": {"total": 3},
            },
        }
        final_fixture = canonical_fixture_observation(game, receipt)
        assert final_fixture is not None
        assert settlement_repository.append_fixture_observations((final_fixture,)) == 1

        result = build_game_result_fact(game, final_fixture, receipt)
        assert result is not None
        assert settlement_repository.append_result(result) is True

        settlement = settlement_repository.settle(
            pick.pick_id,
            result,
            settled_at=datetime(2026, 9, 20, 22, 0, 1, tzinfo=UTC),
        )
        assert settlement.outcome == "WIN"
        assert settlement.profit_per_unit == 1.0
        assert settlement.clv_status == "AVAILABLE"
        assert settlement.closing_observation_id == close_home.observation_id
        assert settlement.closing_odds == 1.85
        assert settlement.clv_probability_delta is not None
        assert settlement.clv_probability_delta > 0
        assert settlement.clv_price_ratio is not None
        assert settlement.clv_price_ratio > 0

        assert (
            settlement_repository.settle(
                pick.pick_id,
                result,
                settled_at=datetime(2026, 9, 20, 22, 1, tzinfo=UTC),
            )
            == settlement
        )

        after_dashboard = settlement_repository.dashboard_snapshot()
        assert after_dashboard["settled_picks"] == before_dashboard["settled_picks"] + 1
        assert after_dashboard["wins"] == before_dashboard["wins"] + 1
        assert after_dashboard["clv_available"] == before_dashboard["clv_available"] + 1
        assert after_dashboard["pending_settlement"] == (
            before_dashboard["pending_settlement"] - 1
        )
        assert after_dashboard["realized_profit_per_unit"] == pytest.approx(
            before_dashboard["realized_profit_per_unit"] + 1.0
        )

        after_health = PostgreSQLEvidenceRepository(connection).health_snapshot()
        assert (
            after_health["game_result_facts"] == before_health["game_result_facts"] + 1
        )
        assert after_health["settled_picks"] == before_health["settled_picks"] + 1
        assert after_health["clv_available"] == before_health["clv_available"] + 1
