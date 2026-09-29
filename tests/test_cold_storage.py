import gzip
import hashlib
import io
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest

from quantbot.baseball.cold_storage import (
    ColdArchivePolicy,
    S3ColdObjectStore,
    VerifiedColdObject,
    policies_from_env,
    restore_archive,
    run_cold_storage_cycle,
)
from quantbot.baseball.db import apply_migrations
from quantbot.baseball.decision_lifecycle import (
    build_model_prediction,
    build_moneyline_pair_evaluations,
)
from quantbot.baseball.decision_repository import PostgreSQLMoneylineDecisionRepository
from quantbot.baseball.evidence import OddsObservation
from quantbot.baseball.fixture_evidence import FixtureObservation
from quantbot.baseball.game_history import GameHistorySnapshot
from quantbot.baseball.game_history_repository import PostgreSQLGameHistoryRepository
from quantbot.baseball.postgres_repository import PostgreSQLEvidenceRepository


class _MemoryColdStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_verified(
        self,
        *,
        key: str,
        body: bytes,
        checksum: str,
    ) -> VerifiedColdObject:
        assert hashlib.sha256(body).hexdigest() == checksum
        self.objects[key] = body
        return VerifiedColdObject(
            ref=f"s3://test-bucket/{key}",
            checksum=checksum,
            size_bytes=len(body),
        )

    def get_verified(self, ref: str, checksum: str) -> bytes:
        prefix = "s3://test-bucket/"
        assert ref.startswith(prefix)
        body = self.objects[ref[len(prefix) :]]
        assert hashlib.sha256(body).hexdigest() == checksum
        return body


def _history_snapshot(
    *,
    provider_game_id: int,
    observed_at: str,
    home_score: int,
    away_score: int,
) -> GameHistorySnapshot:
    return GameHistorySnapshot(
        snapshot_id=str(uuid.uuid4()),
        provider="api-sports-baseball",
        provider_game_id=provider_game_id,
        observed_at=observed_at,
        scheduled_first_pitch="2040-07-01T19:00:00+00:00",
        provider_timezone="UTC",
        status_long="Finished",
        status_short="FT",
        league_id=77,
        season=2040,
        home_team_id=7701,
        home_team_name="Cold Home",
        away_team_id=7702,
        away_team_name="Cold Away",
        home_score=home_score,
        away_score=away_score,
        home_hits=8,
        away_hits=6,
        home_errors=0,
        away_errors=1,
        home_innings={"1": 1},
        away_innings={"1": 0},
        source_payload_ref=f"s3://raw/history-{observed_at}.json",
        source_payload_checksum=("a" if home_score == 4 else "b") * 64,
    )


def _fixture(game_id: str, provider_game_id: int) -> FixtureObservation:
    return FixtureObservation(
        fixture_observation_id=str(uuid.uuid4()),
        game_id=game_id,
        provider="api-sports-baseball",
        provider_game_id=provider_game_id,
        league="Cold Test League",
        league_id=77,
        home_team_id=7701,
        home_team_name="Cold Home",
        away_team_id=7702,
        away_team_name="Cold Away",
        kickoff_at="2040-07-01T19:00:00+00:00",
        provider_status="NS",
        observed_at="2040-07-01T12:00:00+00:00",
        source_payload_ref="s3://raw/cold-fixture.json",
        source_payload_checksum="c" * 64,
        schema_version="1.0",
    )


def _odds(
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
        observed_at="2040-07-01T16:00:00+00:00",
        retrieved_at="2040-07-01T16:00:00+00:00",
        source_payload_ref=f"s3://raw/cold-{observation_id}.json",
        source_payload_checksum="d" * 64,
        schema_version="1.0",
        market_status="open",
        kickoff_at="2040-07-01T19:00:00+00:00",
    )


def test_superseded_game_history_archives_purges_and_restores() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    apply_migrations(Path("."), database_url)

    provider_game_id = 300_000_000 + (uuid.uuid4().int % 500_000_000)
    old = _history_snapshot(
        provider_game_id=provider_game_id,
        observed_at="2040-07-01T22:00:00+00:00",
        home_score=4,
        away_score=2,
    )
    corrected = _history_snapshot(
        provider_game_id=provider_game_id,
        observed_at="2040-07-09T12:00:00+00:00",
        home_score=5,
        away_score=2,
    )
    policy = ColdArchivePolicy(
        table_name="api_sports_game_history_snapshots",
        primary_key="snapshot_id",
        time_column="observed_at",
        archive_mode="SUPERSEDED",
        retention=timedelta(days=2),
    )
    store = _MemoryColdStore()

    with psycopg.connect(database_url) as connection:
        history = PostgreSQLGameHistoryRepository(connection)
        assert history.append_snapshot(old)
        assert history.append_snapshot(corrected)

        summary = run_cold_storage_cycle(
            connection,
            store,
            now=datetime(2003, 1, 10, 12, 0, tzinfo=UTC),
            policies=(policy,),
            max_rows_per_table=100,
            purge_enabled=True,
        )
        connection.commit()

        assert summary["rows_archived"] == 1
        assert summary["tables"][policy.table_name]["archived_rows"] == 1
        latest = history.latest_snapshots_for_season(league_id=77, season=2040)
        selected = [row for row in latest if row.provider_game_id == provider_game_id]
        assert len(selected) == 1
        assert selected[0].snapshot_id == corrected.snapshot_id

        archive_row = connection.execute(
            """
            SELECT archive_id, object_ref, object_sha256, row_count
            FROM cold_storage_archives
            WHERE table_name = %s
            ORDER BY archived_at DESC
            LIMIT 1
            """,
            (policy.table_name,),
        ).fetchone()
        assert archive_row is not None
        archive_id, object_ref, checksum, row_count = archive_row
        assert row_count == 1

        body = store.get_verified(str(object_ref), str(checksum))
        payload = json.loads(gzip.decompress(body))
        assert payload["row_count"] == 1
        assert payload["rows"][0]["snapshot_id"] == old.snapshot_id

        restored = restore_archive(
            connection,
            store,
            archive_id=str(archive_id),
        )
        connection.commit()
        assert restored == 1
        count = connection.execute(
            """
            SELECT COUNT(*)
            FROM api_sports_game_history_snapshots
            WHERE provider_game_id = %s
            """,
            (provider_game_id,),
        ).fetchone()[0]
        assert count == 2


def test_decision_linked_odds_are_never_cold_eligible() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    apply_migrations(Path("."), database_url)

    provider_game_id = 400_000_000 + (uuid.uuid4().int % 400_000_000)
    game_id = str(provider_game_id)
    fixture = _fixture(game_id, provider_game_id)
    home = _odds(
        observation_id=str(uuid.uuid4()),
        game_id=game_id,
        selection="home",
        odds=2.20,
    )
    away = _odds(
        observation_id=str(uuid.uuid4()),
        game_id=game_id,
        selection="away",
        odds=1.75,
    )
    unreferenced = _odds(
        observation_id=str(uuid.uuid4()),
        game_id=game_id,
        selection="home",
        odds=2.15,
    )
    prediction = build_model_prediction(
        game_id=game_id,
        model_version="cold-storage-test",
        feature_snapshot_ref=f"cold-feature-{game_id}",
        source_data_cutoff_at="2040-07-01T15:55:00+00:00",
        predicted_at="2040-07-01T16:01:00+00:00",
        home_probability=0.58,
        away_probability=0.42,
        uncertainty_metric=0.02,
    )
    evaluations = build_moneyline_pair_evaluations(
        prediction,
        home,
        away,
        stage="PRELIMINARY",
        evaluated_at="2040-07-01T16:02:00+00:00",
        min_edge=0.0,
        min_expected_value=0.0,
        max_uncertainty=0.05,
        max_quote_age_seconds=900,
    )
    policy = ColdArchivePolicy(
        table_name="odds_observations",
        primary_key="observation_id",
        time_column="observed_at",
        archive_mode="UNREFERENCED",
        retention=timedelta(days=7),
    )
    store = _MemoryColdStore()

    with psycopg.connect(database_url) as connection:
        evidence = PostgreSQLEvidenceRepository(connection)
        decisions = PostgreSQLMoneylineDecisionRepository(connection)
        evidence.append_fixture_observations((fixture,))
        assert decisions.append_observations((home, away, unreferenced)) == 3
        assert decisions.append_prediction(prediction)
        for evaluation in evaluations:
            decisions.append_evaluation(evaluation)

        summary = run_cold_storage_cycle(
            connection,
            store,
            now=datetime(2040, 7, 10, 12, 0, tzinfo=UTC),
            policies=(policy,),
            max_rows_per_table=100,
            purge_enabled=True,
        )
        connection.commit()

        assert summary["rows_archived"] == 1
        remaining_ids = {
            str(row[0])
            for row in connection.execute(
                """
                SELECT observation_id
                FROM odds_observations
                WHERE observation_id IN (%s, %s, %s)
                """,
                (home.observation_id, away.observation_id, unreferenced.observation_id),
            ).fetchall()
        }
        assert home.observation_id in remaining_ids
        assert away.observation_id in remaining_ids
        assert unreferenced.observation_id not in remaining_ids


class _FakeS3Client:
    def __init__(self, *, corrupt_read: bool = False) -> None:
        self.corrupt_read = corrupt_read
        self.objects: dict[tuple[str, str], tuple[bytes, dict[str, str]]] = {}

    def put_object(self, *, Bucket, Key, Body, Metadata, **kwargs):
        self.objects[(Bucket, Key)] = (bytes(Body), dict(Metadata))

    def head_object(self, *, Bucket, Key):
        body, metadata = self.objects[(Bucket, Key)]
        return {"ContentLength": len(body), "Metadata": metadata}

    def get_object(self, *, Bucket, Key):
        body, _ = self.objects[(Bucket, Key)]
        if self.corrupt_read:
            body += b"corrupt"
        return {"Body": io.BytesIO(body)}


def test_s3_upload_requires_full_sha256_read_back() -> None:
    body = b"archive-object"
    checksum = hashlib.sha256(body).hexdigest()
    good = S3ColdObjectStore(client=_FakeS3Client(), bucket="cold-test")

    verified = good.put_verified(
        key="cold/baseball/test.json.gz",
        body=body,
        checksum=checksum,
    )
    assert verified.checksum == checksum
    assert verified.size_bytes == len(body)

    corrupt = S3ColdObjectStore(
        client=_FakeS3Client(corrupt_read=True),
        bucket="cold-test",
    )
    with pytest.raises(RuntimeError, match="checksum verification"):
        corrupt.put_verified(
            key="cold/baseball/corrupt.json.gz",
            body=body,
            checksum=checksum,
        )


def test_operational_runtime_cycles_archive_after_retention() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    apply_migrations(Path("."), database_url)

    run_id = str(uuid.uuid4())
    old_time = datetime(2000, 1, 1, 0, 0, tzinfo=UTC)
    policy = ColdArchivePolicy(
        table_name="runtime_cycles",
        primary_key="run_id",
        time_column="finished_at",
        archive_mode="AGE",
        retention=timedelta(days=14),
    )
    store = _MemoryColdStore()

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
            VALUES (%s, %s, %s, TRUE, 'collection', 'ready', '{}'::jsonb)
            """,
            (run_id, old_time, old_time),
        )
        connection.commit()

        summary = run_cold_storage_cycle(
            connection,
            store,
            now=datetime(2000, 1, 20, 0, 0, tzinfo=UTC),
            policies=(policy,),
            max_rows_per_table=100,
            purge_enabled=True,
        )
        connection.commit()

        assert summary["rows_archived"] == 1
        assert (
            connection.execute(
                "SELECT 1 FROM runtime_cycles WHERE run_id = %s",
                (run_id,),
            ).fetchone()
            is None
        )


def test_mlb_identity_referenced_fixture_never_becomes_cold_eligible() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    apply_migrations(Path("."), database_url)

    provider_game_id = 500_000_000 + (uuid.uuid4().int % 300_000_000)
    game_id = str(provider_game_id)
    base = _fixture(game_id, provider_game_id)
    old = FixtureObservation(
        **{
            **base.to_dict(),
            "fixture_observation_id": str(uuid.uuid4()),
            "kickoff_at": "2003-01-01T19:00:00+00:00",
            "observed_at": "2003-01-01T12:00:00+00:00",
            "source_payload_ref": "s3://raw/cold-fixture-old.json",
        }
    )
    newer = FixtureObservation(
        **{
            **old.to_dict(),
            "fixture_observation_id": str(uuid.uuid4()),
            "observed_at": "2003-01-09T12:00:00+00:00",
            "source_payload_ref": "s3://raw/cold-fixture-newer.json",
            "source_payload_checksum": "e" * 64,
        }
    )
    mapping_version = f"cold-test-{uuid.uuid4()}"
    policy = ColdArchivePolicy(
        table_name="fixture_observations",
        primary_key="fixture_observation_id",
        time_column="observed_at",
        archive_mode="SUPERSEDED_UNREFERENCED",
        retention=timedelta(days=7),
    )
    store = _MemoryColdStore()

    with psycopg.connect(database_url) as connection:
        evidence = PostgreSQLEvidenceRepository(connection)
        assert evidence.append_fixture_observations((old, newer)) == 2
        connection.execute(
            """
            INSERT INTO official_mlb_team_identity_mappings (
                mapping_id,
                mapping_version,
                api_sports_team_id,
                api_sports_team_name,
                official_mlb_team_id,
                official_mlb_team_name,
                verified_at,
                api_fixture_observation_id,
                api_source_payload_ref,
                api_source_payload_checksum,
                mlb_schedule_source_payload_ref,
                mlb_schedule_source_payload_checksum,
                schema_version,
                canonical_record
            )
            VALUES (
                %s, %s, %s, 'Cold Home', %s, 'Cold MLB Home',
                %s, %s, 's3://raw/api.json', %s,
                's3://raw/mlb.json', %s, '1.0', '{}'::jsonb
            )
            """,
            (
                str(uuid.uuid4()),
                mapping_version,
                old.home_team_id,
                60_000 + (uuid.uuid4().int % 10_000),
                datetime(2003, 1, 9, 13, 0, tzinfo=UTC),
                old.fixture_observation_id,
                "f" * 64,
                "a" * 64,
            ),
        )
        connection.commit()

        summary = run_cold_storage_cycle(
            connection,
            store,
            now=datetime(2040, 7, 10, 12, 0, tzinfo=UTC),
            policies=(policy,),
            max_rows_per_table=100,
            purge_enabled=True,
        )
        connection.commit()

        assert summary["rows_archived"] == 0
        assert (
            connection.execute(
                """
                SELECT 1
                FROM fixture_observations
                WHERE fixture_observation_id = %s
                """,
                (old.fixture_observation_id,),
            ).fetchone()
            is not None
        )



def test_default_production_policies_archive_only_operational_exhaust(
    monkeypatch,
) -> None:
    monkeypatch.delenv("BASEBALL_COLD_POLL_ATTEMPT_DAYS", raising=False)
    monkeypatch.delenv("BASEBALL_COLD_RUNTIME_CYCLE_DAYS", raising=False)
    monkeypatch.delenv("BASEBALL_COLD_COLLECTION_CYCLE_DAYS", raising=False)
    monkeypatch.delenv("BASEBALL_COLD_SCHEDULE_SNAPSHOT_DAYS", raising=False)

    policies = policies_from_env()
    tables = {policy.table_name for policy in policies}

    assert tables == {
        "odds_poll_attempts",
        "runtime_cycles",
        "collection_cycles",
        "api_sports_game_schedule_snapshots",
    }
    assert "api_sports_game_history_snapshots" not in tables
    assert "fixture_observations" not in tables
    assert "odds_observations" not in tables
