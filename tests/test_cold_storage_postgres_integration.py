import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from quantbot.baseball.cold_archive import LocalColdArchiveStore
from quantbot.baseball.cold_storage import (
    archive_dataset_batch,
    archive_policies_from_env,
    restore_archive,
)
from quantbot.baseball.db import apply_migrations
from quantbot.baseball.decision_lifecycle import (
    build_model_prediction,
    build_moneyline_pair_evaluations,
)
from quantbot.baseball.decision_repository import PostgreSQLMoneylineDecisionRepository
from quantbot.baseball.evidence import OddsObservation
from quantbot.baseball.fixture_evidence import FixtureObservation
from quantbot.baseball.postgres_repository import PostgreSQLEvidenceRepository


def _database_url() -> str:
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    return value


def _policy(dataset: str):
    return next(
        policy for policy in archive_policies_from_env() if policy.dataset == dataset
    )


def test_runtime_cycle_archives_and_restores_exact_row(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_url = _database_url()
    apply_migrations(Path("."), database_url)
    monkeypatch.setenv("BASEBALL_COLD_RUNTIME_RETENTION_DAYS", "1")

    run_id = str(uuid.uuid4())
    started = datetime(2039, 1, 1, 0, 0, tzinfo=UTC)
    stats = {"status": "old-runtime", "counter": 7}

    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            INSERT INTO runtime_cycles (
                run_id,
                started_at,
                finished_at,
                collection_enabled,
                mode,
                status,
                stats
            )
            VALUES (%s, %s, %s, TRUE, 'collection', 'ready', %s::jsonb)
            """,
            (run_id, started, started, '{"counter":7,"status":"old-runtime"}'),
        )
        connection.commit()

        store = LocalColdArchiveStore(tmp_path / "bucket")
        result = archive_dataset_batch(
            connection,
            store,
            _policy("runtime-cycles"),
            now=datetime(2040, 1, 1, 0, 0, tzinfo=UTC),
            batch_rows=10,
        )

        assert result["status"] == "ARCHIVED"
        assert result["rows_purged"] >= 1
        archived = connection.execute(
            "SELECT 1 FROM runtime_cycles WHERE run_id = %s",
            (run_id,),
        ).fetchone()
        assert archived is None

        archive_id = str(result["archive_id"])
        manifest = connection.execute(
            """
            SELECT row_count, object_checksum, object_ref
            FROM cold_archive_manifests
            WHERE archive_id = %s
            """,
            (archive_id,),
        ).fetchone()
        assert manifest is not None
        assert int(manifest[0]) >= 1
        assert len(str(manifest[1])) == 64
        assert str(manifest[2]).startswith("file://")

        restored = restore_archive(
            connection,
            store,
            archive_id=archive_id,
        )
        assert restored["status"] == "COMPLETE"

        row = connection.execute(
            """
            SELECT
                started_at,
                finished_at,
                collection_enabled,
                mode,
                status,
                stats
            FROM runtime_cycles
            WHERE run_id = %s
            """,
            (run_id,),
        ).fetchone()
        assert row is not None
        assert row[0] == started
        assert row[1] == started
        assert row[2] is True
        assert row[3] == "collection"
        assert row[4] == "ready"
        assert row[5] == stats

        restore_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM cold_archive_restore_events
            WHERE archive_id = %s
            """,
            (archive_id,),
        ).fetchone()[0]
        assert int(restore_count) == 1


def _quote(
    *,
    game_id: str,
    observation_id: str,
    selection: str,
    odds: float,
    observed_at: str,
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
        observed_at=observed_at,
        retrieved_at=observed_at,
        source_payload_ref=f"s3://raw/{observation_id}.json",
        source_payload_checksum="a" * 64,
        schema_version="1.0",
        market_status="open",
        kickoff_at="2039-01-02T19:00:00+00:00",
    )


def test_referenced_odds_stay_hot_while_unreferenced_old_quote_is_archived(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_url = _database_url()
    apply_migrations(Path("."), database_url)
    monkeypatch.setenv("BASEBALL_COLD_ODDS_RETENTION_DAYS", "1")

    provider_game_id = 300_000_000 + (uuid.uuid4().int % 500_000_000)
    game_id = str(provider_game_id)
    fixture = FixtureObservation(
        fixture_observation_id=str(uuid.uuid4()),
        game_id=game_id,
        provider="api-sports-baseball",
        provider_game_id=provider_game_id,
        league="Cold Safety League",
        league_id=99,
        home_team_id=991,
        home_team_name="Cold Home",
        away_team_id=992,
        away_team_name="Cold Away",
        kickoff_at="2039-01-02T19:00:00+00:00",
        provider_status="NS",
        observed_at="2039-01-02T16:00:00+00:00",
        source_payload_ref="s3://raw/cold-safety-fixture.json",
        source_payload_checksum="b" * 64,
        schema_version="1.0",
    )
    home = _quote(
        game_id=game_id,
        observation_id=str(uuid.uuid4()),
        selection="home",
        odds=2.10,
        observed_at="2039-01-02T16:05:00+00:00",
    )
    away = _quote(
        game_id=game_id,
        observation_id=str(uuid.uuid4()),
        selection="away",
        odds=1.80,
        observed_at="2039-01-02T16:05:00+00:00",
    )
    orphan = _quote(
        game_id=game_id,
        observation_id=str(uuid.uuid4()),
        selection="home",
        odds=2.20,
        observed_at="2039-01-02T15:00:00+00:00",
    )
    prediction = build_model_prediction(
        game_id=game_id,
        model_version="team-strength-poisson-baseline-v1",
        feature_snapshot_ref=f"feature-{game_id}",
        source_data_cutoff_at="2039-01-02T16:00:00+00:00",
        predicted_at="2039-01-02T16:01:00+00:00",
        home_probability=0.55,
        away_probability=0.45,
        uncertainty_metric=0.025,
    )
    evaluations = build_moneyline_pair_evaluations(
        prediction,
        home,
        away,
        stage="PRELIMINARY",
        evaluated_at="2039-01-02T16:06:00+00:00",
        min_edge=0.02,
        min_expected_value=0.0,
        max_uncertainty=0.05,
        max_quote_age_seconds=900,
    )

    with psycopg.connect(database_url) as connection:
        evidence = PostgreSQLEvidenceRepository(connection)
        decisions = PostgreSQLMoneylineDecisionRepository(connection)
        assert evidence.append_fixture_observations((fixture,)) == 1
        assert decisions.append_observations((home, away, orphan)) == 3
        assert decisions.append_prediction(prediction)
        for evaluation in evaluations:
            assert decisions.append_evaluation(evaluation)

        store = LocalColdArchiveStore(tmp_path / "bucket")
        result = archive_dataset_batch(
            connection,
            store,
            _policy("odds-observations"),
            now=datetime(2040, 1, 1, 0, 0, tzinfo=UTC),
            batch_rows=100,
        )
        assert result["status"] == "ARCHIVED"

        ids = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT observation_id
                FROM odds_observations
                WHERE observation_id = ANY(%s::uuid[])
                """,
                ([home.observation_id, away.observation_id, orphan.observation_id],),
            ).fetchall()
        }

        assert home.observation_id in ids
        assert away.observation_id in ids
        assert orphan.observation_id not in ids
