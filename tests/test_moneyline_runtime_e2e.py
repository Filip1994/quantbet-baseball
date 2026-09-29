import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from quantbot.baseball.db import apply_migrations
from quantbot.baseball.decision_repository import PostgreSQLMoneylineDecisionRepository
from quantbot.baseball.evidence import OddsObservation
from quantbot.baseball.feature_snapshot_repository import (
    PostgreSQLFeatureSnapshotRepository,
)
from quantbot.baseball.fixture_evidence import FixtureObservation
from quantbot.baseball.moneyline_core_materialization import (
    materialize_due_moneyline_core_v1_features,
)
from quantbot.baseball.moneyline_prediction_materialization import (
    materialize_due_baseline_predictions,
)
from quantbot.baseball.moneyline_registration import MoneylineDecisionPolicy
from quantbot.baseball.moneyline_registration_materialization import (
    materialize_due_moneyline_registrations,
)
from quantbot.baseball.moneyline_value_evaluation import (
    materialize_due_moneyline_evaluations,
)
from quantbot.baseball.postgres_repository import PostgreSQLEvidenceRepository
from quantbot.baseball.provider_data import TeamStatisticsSnapshot
from quantbot.baseball.provider_data_repository import PostgreSQLProviderDataRepository
from quantbot.baseball.raw_archive import ArchiveReceipt


def _team_stats(
    *,
    league_id: int,
    team_id: int,
    team_name: str,
    observed_at: str,
    home_strength: bool,
) -> TeamStatisticsSnapshot:
    if home_strength:
        overall_rf, context_rf = 6.0, 6.5
        overall_ra, context_ra = 3.5, 3.2
        wins_all, split_wins = 62, 34
    else:
        overall_rf, context_rf = 3.8, 3.6
        overall_ra, context_ra = 5.8, 6.0
        wins_all, split_wins = 38, 18

    games_all = 100
    games_home = 50
    games_away = 50
    losses_all = games_all - wins_all
    return TeamStatisticsSnapshot(
        snapshot_id=str(uuid.uuid4()),
        provider="api-sports-baseball",
        league_id=league_id,
        season=2040,
        team_id=team_id,
        team_name=team_name,
        observed_at=observed_at,
        games_played_all=games_all,
        games_played_home=games_home,
        games_played_away=games_away,
        wins_all=wins_all,
        wins_home=split_wins,
        wins_away=wins_all - split_wins,
        win_pct_all=wins_all / games_all,
        win_pct_home=split_wins / games_home,
        win_pct_away=(wins_all - split_wins) / games_away,
        losses_all=losses_all,
        losses_home=games_home - split_wins,
        losses_away=games_away - (wins_all - split_wins),
        loss_pct_all=losses_all / games_all,
        loss_pct_home=(games_home - split_wins) / games_home,
        loss_pct_away=(games_away - (wins_all - split_wins)) / games_away,
        runs_for_total_all=overall_rf * games_all,
        runs_for_total_home=context_rf * games_home,
        runs_for_total_away=overall_rf * games_away,
        runs_for_avg_all=overall_rf,
        runs_for_avg_home=context_rf,
        runs_for_avg_away=overall_rf,
        runs_against_total_all=overall_ra * games_all,
        runs_against_total_home=context_ra * games_home,
        runs_against_total_away=overall_ra * games_away,
        runs_against_avg_all=overall_ra,
        runs_against_avg_home=context_ra,
        runs_against_avg_away=overall_ra,
        source_payload_ref=f"s3://raw/runtime-e2e-team-{team_id}.json",
        source_payload_checksum=("a" if home_strength else "b") * 64,
    )


def _opening_quote(
    *,
    game_id: str,
    selection: str,
    odds: float,
) -> OddsObservation:
    return OddsObservation(
        observation_id=str(uuid.uuid4()),
        game_id=game_id,
        market_family="moneyline",
        line=None,
        selection=selection,
        bookmaker="Bet365",
        decimal_odds=odds,
        raw_price=str(odds),
        observed_at="2040-07-04T16:04:00+00:00",
        retrieved_at="2040-07-04T16:04:00+00:00",
        source_payload_ref=f"s3://raw/runtime-e2e-{selection}.json",
        source_payload_checksum="c" * 64,
        schema_version="1.0",
        market_status="open",
        kickoff_at="2040-07-04T19:30:00+00:00",
    )


class _FreshQuoteClient:
    def __init__(self, provider_game_id: int) -> None:
        self.provider_game_id = provider_game_id
        self.request_count = 0

    def odds_with_receipt(self, game_id: int):
        assert game_id == self.provider_game_id
        self.request_count += 1
        return (
            [
                {
                    "bookmakers": [
                        {
                            "name": "Bet365",
                            "bets": [
                                {
                                    "name": "Moneyline",
                                    "values": [
                                        {"value": "Home", "odd": "1.65"},
                                        {"value": "Away", "odd": "2.30"},
                                    ],
                                }
                            ],
                        }
                    ]
                }
            ],
            ArchiveReceipt(
                ref="s3://raw/runtime-e2e-final.json",
                checksum="d" * 64,
                captured_at="2040-07-04T16:05:30+00:00",
            ),
        )


class _Clock:
    def __init__(self) -> None:
        self.values = iter(
            (
                datetime(2040, 7, 4, 16, 5, 20, tzinfo=UTC),
                datetime(2040, 7, 4, 16, 5, 31, tzinfo=UTC),
                datetime(2040, 7, 4, 16, 5, 32, tzinfo=UTC),
                datetime(2040, 7, 4, 16, 5, 33, tzinfo=UTC),
            )
        )

    def __call__(self) -> datetime:
        return next(self.values)


def test_postgres_runtime_chain_reaches_registered_paper_pick() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    apply_migrations(Path("."), database_url)

    provider_game_id = 200_000_000 + (uuid.uuid4().int % 700_000_000)
    game_id = str(provider_game_id)
    league_id = 88_000 + (uuid.uuid4().int % 10_000)
    home_team_id = 700_000 + (uuid.uuid4().int % 100_000)
    away_team_id = 800_000 + (uuid.uuid4().int % 100_000)
    now = datetime(2040, 7, 4, 16, 5, tzinfo=UTC)

    fixture = FixtureObservation(
        fixture_observation_id=str(uuid.uuid4()),
        game_id=game_id,
        provider="api-sports-baseball",
        provider_game_id=provider_game_id,
        league="Runtime E2E League",
        league_id=league_id,
        home_team_id=home_team_id,
        home_team_name="Runtime Home",
        away_team_id=away_team_id,
        away_team_name="Runtime Away",
        kickoff_at="2040-07-04T19:30:00+00:00",
        provider_status="NS",
        observed_at="2040-07-04T16:00:00+00:00",
        source_payload_ref="s3://raw/runtime-e2e-fixture.json",
        source_payload_checksum="e" * 64,
        schema_version="1.0",
    )
    home_quote = _opening_quote(game_id=game_id, selection="home", odds=1.70)
    away_quote = _opening_quote(game_id=game_id, selection="away", odds=2.20)

    with psycopg.connect(database_url) as connection:
        evidence = PostgreSQLEvidenceRepository(connection)
        provider = PostgreSQLProviderDataRepository(connection)
        features = PostgreSQLFeatureSnapshotRepository(connection)
        decisions = PostgreSQLMoneylineDecisionRepository(connection)

        assert evidence.append_fixture_observations((fixture,)) == 1
        assert decisions.append_observations((home_quote, away_quote)) == 2
        assert provider.append_team_statistics(
            _team_stats(
                league_id=league_id,
                team_id=home_team_id,
                team_name="Runtime Home",
                observed_at="2040-07-04T16:01:00+00:00",
                home_strength=True,
            )
        )
        assert provider.append_team_statistics(
            _team_stats(
                league_id=league_id,
                team_id=away_team_id,
                team_name="Runtime Away",
                observed_at="2040-07-04T16:01:00+00:00",
                home_strength=False,
            )
        )

        feature_result = materialize_due_moneyline_core_v1_features(
            evidence,
            provider,
            features,
            now=now,
            league_ids=None,
            horizon_minutes=360,
            max_games=1,
        )
        assert feature_result["status"] == "COMPLETE"
        assert feature_result["snapshots_inserted"] == 1

        prediction_result = materialize_due_baseline_predictions(
            features,
            decisions,
            now=now,
            horizon_minutes=360,
            max_predictions=1,
        )
        assert prediction_result["status"] == "COMPLETE"
        assert prediction_result["predictions_inserted"] == 1
        assert prediction_result["projection_failures"] == 0

        evaluation_result = materialize_due_moneyline_evaluations(
            decisions,
            now=now,
            horizon_minutes=360,
            max_games=1,
            min_edge=0.02,
            min_expected_value=0.0,
            max_uncertainty=0.05,
            max_quote_age_seconds=900,
        )
        assert evaluation_result["status"] == "COMPLETE"
        assert evaluation_result["candidate_evaluations"] >= 1
        assert evaluation_result["evaluation_failures"] == 0

        client = _FreshQuoteClient(provider_game_id)
        registration_result = materialize_due_moneyline_registrations(
            client,
            decisions,
            now=now,
            horizon_minutes=360,
            max_candidates=1,
            policy=MoneylineDecisionPolicy(
                min_edge=0.02,
                min_expected_value=0.0,
                max_uncertainty=0.05,
                preliminary_max_quote_age_seconds=900,
                final_max_quote_age_seconds=120,
            ),
            clock=_Clock(),
        )
        assert registration_result["status"] == "COMPLETE"
        assert registration_result["verifications_ready"] == 1
        assert registration_result["picks_registered"] == 1
        assert registration_result["registration_failures"] == 0
        assert registration_result["provider_calls"] == 1

        health = evidence.health_snapshot()
        assert health["feature_snapshots"] >= 1
        assert health["model_predictions"] >= 1
        assert health["value_evaluations"] >= 2
        assert health["final_quote_verifications"] >= 1
        assert health["registered_picks"] >= 1
