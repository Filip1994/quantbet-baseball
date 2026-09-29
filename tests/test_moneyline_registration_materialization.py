import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest

from quantbot.baseball.db import apply_migrations
from quantbot.baseball.decision_lifecycle import (
    build_model_prediction,
    build_moneyline_pair_evaluations,
)
from quantbot.baseball.decision_repository import (
    PostgreSQLMoneylineDecisionRepository,
)
from quantbot.baseball.evidence import OddsObservation
from quantbot.baseball.fixture_evidence import FixtureObservation
from quantbot.baseball.moneyline_registration_materialization import (
    materialize_due_moneyline_registrations,
)
from quantbot.baseball.postgres_repository import PostgreSQLEvidenceRepository


class _Client:
    def __init__(self) -> None:
        self.request_count = 4


class _Repository:
    def __init__(self, candidates) -> None:
        self.candidates = candidates

    def due_preliminary_candidates_for_registration(
        self,
        *,
        as_of,
        horizon_minutes,
        limit,
    ):
        assert as_of == datetime(2035, 7, 4, 16, 5, tzinfo=UTC)
        assert horizon_minutes == 360
        assert limit == 1
        return self.candidates[:limit]


def test_registration_materializer_registers_bounded_ready_candidate() -> None:
    candidate = SimpleNamespace(evaluation_id="candidate-1")
    repository = _Repository((candidate,))
    client = _Client()

    def register(client, repository, evaluation_id, *, clock, policy):
        assert evaluation_id == "candidate-1"
        assert clock().tzinfo is not None
        assert policy.final_max_quote_age_seconds == 120.0
        client.request_count += 1
        return SimpleNamespace(
            verification=SimpleNamespace(status="READY"),
            pick=SimpleNamespace(pick_id="pick-1"),
        )

    now = datetime(2035, 7, 4, 16, 5, tzinfo=UTC)
    result = materialize_due_moneyline_registrations(
        client,
        repository,
        now=now,
        max_candidates=1,
        clock=lambda: now,
        register=register,
    )

    assert result["status"] == "COMPLETE"
    assert result["candidates_seen"] == 1
    assert result["candidates_considered"] == 1
    assert result["verifications_ready"] == 1
    assert result["verifications_rejected"] == 0
    assert result["picks_registered"] == 1
    assert result["registration_failures"] == 0
    assert result["provider_calls"] == 1


def test_registration_materializer_treats_final_rejection_as_completed_work() -> None:
    candidate = SimpleNamespace(evaluation_id="candidate-2")
    repository = _Repository((candidate,))
    client = _Client()

    def register(client, repository, evaluation_id, *, clock, policy):
        client.request_count += 1
        return SimpleNamespace(
            verification=SimpleNamespace(status="REJECTED"),
            pick=None,
        )

    result = materialize_due_moneyline_registrations(
        client,
        repository,
        now=datetime(2035, 7, 4, 16, 5, tzinfo=UTC),
        register=register,
    )

    assert result["status"] == "COMPLETE"
    assert result["verifications_ready"] == 0
    assert result["verifications_rejected"] == 1
    assert result["picks_registered"] == 0
    assert result["registration_failures"] == 0
    assert result["provider_calls"] == 1


def _observation(
    *,
    observation_id: str,
    game_id: str,
    selection: str,
    odds: float,
) -> OddsObservation:
    return OddsObservation(
        observation_id=observation_id,
        game_id=game_id,
        market_family="moneyline",
        line=None,
        selection=selection,
        bookmaker="Bet365",
        decimal_odds=odds,
        raw_price=str(odds),
        observed_at="2035-07-04T16:04:00+00:00",
        retrieved_at="2035-07-04T16:04:00+00:00",
        source_payload_ref=f"s3://raw/{observation_id}.json",
        source_payload_checksum="a" * 64,
        schema_version="1.0",
        market_status="open",
        kickoff_at="2035-07-04T19:00:00+00:00",
    )


def test_postgres_exposes_best_due_candidate_for_registration() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    apply_migrations(Path("."), database_url)

    provider_game_id = 100_000_000 + (uuid.uuid4().int % 800_000_000)
    game_id = str(provider_game_id)
    fixture = FixtureObservation(
        fixture_observation_id=str(uuid.uuid4()),
        game_id=game_id,
        provider="api-sports-baseball",
        provider_game_id=provider_game_id,
        league="Test League",
        league_id=1,
        home_team_id=990011,
        home_team_name="Registration Home",
        away_team_id=990012,
        away_team_name="Registration Away",
        kickoff_at="2035-07-04T19:00:00+00:00",
        provider_status="NS",
        observed_at="2035-07-04T16:00:00+00:00",
        source_payload_ref="s3://raw/registration-fixture.json",
        source_payload_checksum="b" * 64,
        schema_version="1.0",
    )
    home = _observation(
        observation_id=str(uuid.uuid4()),
        game_id=game_id,
        selection="home",
        odds=2.10,
    )
    away = _observation(
        observation_id=str(uuid.uuid4()),
        game_id=game_id,
        selection="away",
        odds=1.80,
    )
    prediction = build_model_prediction(
        game_id=game_id,
        model_version="team-strength-poisson-baseline-v1",
        feature_snapshot_ref=f"feature-{game_id}",
        source_data_cutoff_at="2035-07-04T16:00:00+00:00",
        predicted_at="2035-07-04T16:01:00+00:00",
        home_probability=0.55,
        away_probability=0.45,
        uncertainty_metric=0.025,
    )
    evaluations = build_moneyline_pair_evaluations(
        prediction,
        home,
        away,
        stage="PRELIMINARY",
        evaluated_at="2035-07-04T16:05:00+00:00",
        min_edge=0.02,
        min_expected_value=0.0,
        max_uncertainty=0.05,
        max_quote_age_seconds=900,
    )
    candidate = next(item for item in evaluations if item.outcome == "CANDIDATE")

    with psycopg.connect(database_url) as connection:
        evidence = PostgreSQLEvidenceRepository(connection)
        evidence.append_fixture_observations((fixture,))
        decision = PostgreSQLMoneylineDecisionRepository(connection)
        decision.append_observations((home, away))
        decision.append_prediction(prediction)
        for evaluation in evaluations:
            decision.append_evaluation(evaluation)

        due = decision.due_preliminary_candidates_for_registration(
            as_of=datetime(2035, 7, 4, 16, 6, tzinfo=UTC),
            horizon_minutes=360,
            limit=1,
        )

    assert len(due) == 1
    assert due[0].evaluation_id == candidate.evaluation_id
    assert due[0].game_id == game_id
