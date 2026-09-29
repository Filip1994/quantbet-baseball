"""Bounded hot/cold retention for Baseball production evidence."""

from __future__ import annotations

import gzip
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from psycopg import sql

from .cold_archive import ColdArchiveStore, sha256_file

_ARCHIVE_LOCK_KEY = 726478920260920
_ARCHIVE_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/cold-archive/v1",
)
_RESTORE_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/cold-archive-restore/v1",
)
_SCHEMA_VERSION = "1.0"


_ODDS_UNREFERENCED = """
NOT EXISTS (
    SELECT 1
    FROM value_evaluations v
    WHERE t.observation_id IN (
        v.home_observation_id,
        v.away_observation_id,
        v.selected_observation_id
    )
)
AND NOT EXISTS (
    SELECT 1
    FROM final_quote_verifications q
    WHERE t.observation_id IN (
        q.returned_home_observation_id,
        q.returned_away_observation_id
    )
)
AND NOT EXISTS (
    SELECT 1
    FROM registered_picks p
    WHERE p.entry_observation_id = t.observation_id
)
AND NOT EXISTS (
    SELECT 1
    FROM pick_closing_finalizations c
    WHERE t.observation_id IN (
        c.candidate_home_observation_id,
        c.candidate_away_observation_id,
        c.closing_observation_id
    )
)
AND NOT EXISTS (
    SELECT 1
    FROM pick_settlements s
    WHERE s.closing_observation_id = t.observation_id
)
"""

_FIXTURE_UNREFERENCED_AND_NOT_LATEST = """
EXISTS (
    SELECT 1
    FROM fixture_observations newer
    WHERE newer.game_id = t.game_id
      AND (
          newer.observed_at > t.observed_at
          OR (
              newer.observed_at = t.observed_at
              AND newer.fixture_observation_id > t.fixture_observation_id
          )
      )
)
AND NOT EXISTS (
    SELECT 1
    FROM pick_closing_finalizations c
    WHERE c.fixture_observation_id = t.fixture_observation_id
)
AND NOT EXISTS (
    SELECT 1
    FROM game_result_facts r
    WHERE r.fixture_observation_id = t.fixture_observation_id
)
AND NOT EXISTS (
    SELECT 1
    FROM official_mlb_team_identity_mappings m
    WHERE m.api_fixture_observation_id = t.fixture_observation_id
)
AND NOT EXISTS (
    SELECT 1
    FROM official_mlb_game_identity_links g
    WHERE g.api_fixture_observation_id = t.fixture_observation_id
)
"""


@dataclass(frozen=True, slots=True)
class ArchivePolicy:
    dataset: str
    table: str
    primary_key: str
    event_column: str
    cutoff_column: str
    retention_days: int
    extra_predicate: str = "TRUE"

    def __post_init__(self) -> None:
        if self.retention_days < 1:
            raise ValueError("retention_days must be positive")


def _retention(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    value = default if not raw else int(raw)
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def archive_policies_from_env() -> tuple[ArchivePolicy, ...]:
    """Return conservative policies that do not remove decision lineage."""

    return (
        ArchivePolicy(
            dataset="runtime-cycles",
            table="runtime_cycles",
            primary_key="run_id",
            event_column="finished_at",
            cutoff_column="finished_at",
            retention_days=_retention(
                "BASEBALL_COLD_RUNTIME_RETENTION_DAYS",
                14,
            ),
        ),
        ArchivePolicy(
            dataset="collection-cycles",
            table="collection_cycles",
            primary_key="cycle_id",
            event_column="finished_at",
            cutoff_column="finished_at",
            retention_days=_retention(
                "BASEBALL_COLD_COLLECTION_RETENTION_DAYS",
                14,
            ),
        ),
        ArchivePolicy(
            dataset="odds-poll-attempts",
            table="odds_poll_attempts",
            primary_key="poll_attempt_id",
            event_column="attempted_at",
            cutoff_column="kickoff_at",
            retention_days=_retention(
                "BASEBALL_COLD_POLL_RETENTION_DAYS",
                14,
            ),
        ),
        ArchivePolicy(
            dataset="schedule-snapshots",
            table="api_sports_game_schedule_snapshots",
            primary_key="snapshot_id",
            event_column="observed_at",
            cutoff_column="observed_at",
            retention_days=_retention(
                "BASEBALL_COLD_SCHEDULE_RETENTION_DAYS",
                14,
            ),
        ),
        ArchivePolicy(
            dataset="fixture-observations",
            table="fixture_observations",
            primary_key="fixture_observation_id",
            event_column="observed_at",
            cutoff_column="kickoff_at",
            retention_days=_retention(
                "BASEBALL_COLD_FIXTURE_RETENTION_DAYS",
                30,
            ),
            extra_predicate=_FIXTURE_UNREFERENCED_AND_NOT_LATEST,
        ),
        ArchivePolicy(
            dataset="odds-observations",
            table="odds_observations",
            primary_key="observation_id",
            event_column="observed_at",
            cutoff_column="kickoff_at",
            retention_days=_retention(
                "BASEBALL_COLD_ODDS_RETENTION_DAYS",
                30,
            ),
            extra_predicate=_ODDS_UNREFERENCED,
        ),
    )


def _candidate_query(policy: ArchivePolicy) -> sql.Composed:
    return sql.SQL(
        """
        SELECT
            t.{primary_key}::text,
            t.{event_column},
            to_jsonb(t)::text
        FROM {table} AS t
        WHERE t.{cutoff_column} < %s
          AND ({extra_predicate})
        ORDER BY t.{event_column}, t.{primary_key}
        LIMIT %s
        """
    ).format(
        primary_key=sql.Identifier(policy.primary_key),
        event_column=sql.Identifier(policy.event_column),
        table=sql.Identifier(policy.table),
        cutoff_column=sql.Identifier(policy.cutoff_column),
        extra_predicate=sql.SQL(policy.extra_predicate),
    )


def _delete_query(policy: ArchivePolicy) -> sql.Composed:
    return sql.SQL(
        """
        DELETE FROM {table} AS t
        WHERE t.{primary_key}::text = ANY(%s)
          AND t.{cutoff_column} < %s
          AND ({extra_predicate})
        """
    ).format(
        table=sql.Identifier(policy.table),
        primary_key=sql.Identifier(policy.primary_key),
        cutoff_column=sql.Identifier(policy.cutoff_column),
        extra_predicate=sql.SQL(policy.extra_predicate),
    )


def _archive_key(
    policy: ArchivePolicy,
    *,
    exported_at: datetime,
    checksum: str,
    row_count: int,
) -> str:
    stamp = exported_at.strftime("%Y%m%dT%H%M%S.%fZ")
    return (
        "cold-storage/baseball/v1/"
        f"{policy.dataset}/{exported_at:%Y/%m/%d}/"
        f"{stamp}_{row_count}_{checksum[:16]}.jsonl.gz"
    )


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def archive_dataset_batch(
    connection: Any,
    store: ColdArchiveStore,
    policy: ArchivePolicy,
    *,
    now: datetime,
    batch_rows: int,
) -> dict[str, Any]:
    """Archive one verified batch and purge exactly those eligible rows."""

    if batch_rows < 1:
        raise ValueError("batch_rows must be positive")
    current = now.astimezone(UTC)
    cutoff = current - timedelta(days=policy.retention_days)

    rows = connection.execute(
        _candidate_query(policy),
        (cutoff, batch_rows),
    ).fetchall()
    connection.commit()
    if not rows:
        return {
            "dataset": policy.dataset,
            "status": "NO_ELIGIBLE_ROWS",
            "rows_purged": 0,
            "compressed_bytes": 0,
            "object_ref": None,
        }

    row_ids = [str(row[0]) for row in rows]
    event_times = [row[1].astimezone(UTC) for row in rows]
    min_event_at = min(event_times)
    max_event_at = max(event_times)

    with tempfile.TemporaryDirectory(prefix="baseball-cold-") as temp_dir:
        archive_path = Path(temp_dir) / "rows.jsonl.gz"
        with archive_path.open("wb") as raw_handle:
            with gzip.GzipFile(
                filename="",
                mode="wb",
                fileobj=raw_handle,
                mtime=0,
            ) as gzip_handle:
                for row in rows:
                    gzip_handle.write(str(row[2]).encode("utf-8"))
                    gzip_handle.write(b"\n")

        checksum = sha256_file(archive_path)
        exported_at = datetime.now(UTC)
        key = _archive_key(
            policy,
            exported_at=exported_at,
            checksum=checksum,
            row_count=len(rows),
        )
        receipt = store.put_verified_file(
            key=key,
            path=archive_path,
            checksum=checksum,
        )

    verified_at = datetime.now(UTC)
    purged_at = verified_at
    archive_id = str(uuid.uuid5(_ARCHIVE_NAMESPACE, receipt.ref))
    manifest = {
        "archive_id": archive_id,
        "dataset": policy.dataset,
        "source_table": policy.table,
        "object_ref": receipt.ref,
        "object_checksum": receipt.checksum,
        "archive_format": "jsonl.gz",
        "retention_cutoff_at": cutoff.isoformat(),
        "min_event_at": min_event_at.isoformat(),
        "max_event_at": max_event_at.isoformat(),
        "row_count": len(rows),
        "compressed_bytes": receipt.compressed_bytes,
        "exported_at": exported_at.isoformat(),
        "verified_at": verified_at.isoformat(),
        "purged_at": purged_at.isoformat(),
        "schema_version": _SCHEMA_VERSION,
    }

    with connection.transaction():
        connection.execute(
            """
            INSERT INTO cold_archive_manifests (
                archive_id,
                dataset,
                source_table,
                object_ref,
                object_checksum,
                archive_format,
                retention_cutoff_at,
                min_event_at,
                max_event_at,
                row_count,
                compressed_bytes,
                exported_at,
                verified_at,
                purged_at,
                schema_version,
                canonical_record
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
            )
            """,
            (
                archive_id,
                policy.dataset,
                policy.table,
                receipt.ref,
                receipt.checksum,
                "jsonl.gz",
                cutoff,
                min_event_at,
                max_event_at,
                len(rows),
                receipt.compressed_bytes,
                exported_at,
                verified_at,
                purged_at,
                _SCHEMA_VERSION,
                _canonical_json(manifest),
            ),
        )
        deleted = connection.execute(
            _delete_query(policy),
            (row_ids, cutoff),
        ).rowcount
        if deleted != len(rows):
            raise RuntimeError(
                "cold archive eligibility changed before purge; "
                f"expected {len(rows)} rows, deleted {deleted}"
            )

    return {
        "dataset": policy.dataset,
        "status": "ARCHIVED",
        "rows_purged": len(rows),
        "compressed_bytes": receipt.compressed_bytes,
        "object_ref": receipt.ref,
        "archive_id": archive_id,
    }


def _run_already_completed(connection: Any, run_date: Any) -> bool:
    row = connection.execute(
        "SELECT 1 FROM cold_archive_runs WHERE run_date = %s",
        (run_date,),
    ).fetchone()
    connection.commit()
    return row is not None


def run_cold_archive_once(
    connection: Any,
    store: ColdArchiveStore,
    *,
    now: datetime,
    run_hour_utc: int = 4,
    batch_rows: int = 5000,
    policies: tuple[ArchivePolicy, ...] | None = None,
) -> dict[str, Any]:
    """Run at most one bounded verified archival pass per UTC day."""

    current = now.astimezone(UTC)
    if not 0 <= run_hour_utc <= 23:
        raise ValueError("run_hour_utc must be between 0 and 23")
    if batch_rows < 1:
        raise ValueError("batch_rows must be positive")
    if current.hour < run_hour_utc:
        return {
            "status": "BEFORE_WINDOW",
            "objects_written": 0,
            "rows_purged": 0,
            "compressed_bytes": 0,
        }
    if _run_already_completed(connection, current.date()):
        return {
            "status": "ALREADY_DONE",
            "objects_written": 0,
            "rows_purged": 0,
            "compressed_bytes": 0,
        }

    acquired = bool(
        connection.execute(
            "SELECT pg_try_advisory_lock(%s)",
            (_ARCHIVE_LOCK_KEY,),
        ).fetchone()[0]
    )
    connection.commit()
    if not acquired:
        return {
            "status": "LOCK_BUSY",
            "objects_written": 0,
            "rows_purged": 0,
            "compressed_bytes": 0,
        }

    started_at = datetime.now(UTC)
    summaries: list[dict[str, Any]] = []
    try:
        for policy in policies or archive_policies_from_env():
            summaries.append(
                archive_dataset_batch(
                    connection,
                    store,
                    policy,
                    now=current,
                    batch_rows=batch_rows,
                )
            )

        objects_written = sum(
            1 for item in summaries if item["status"] == "ARCHIVED"
        )
        rows_purged = sum(int(item["rows_purged"]) for item in summaries)
        compressed_bytes = sum(
            int(item["compressed_bytes"]) for item in summaries
        )
        finished_at = datetime.now(UTC)
        run_payload = {
            "run_date": current.date().isoformat(),
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "status": "SUCCESS",
            "objects_written": objects_written,
            "rows_purged": rows_purged,
            "compressed_bytes": compressed_bytes,
            "datasets": summaries,
            "schema_version": _SCHEMA_VERSION,
        }
        with connection.transaction():
            connection.execute(
                """
                INSERT INTO cold_archive_runs (
                    run_date,
                    started_at,
                    finished_at,
                    status,
                    objects_written,
                    rows_purged,
                    compressed_bytes,
                    schema_version,
                    canonical_record
                )
                VALUES (%s, %s, %s, 'SUCCESS', %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (run_date) DO NOTHING
                """,
                (
                    current.date(),
                    started_at,
                    finished_at,
                    objects_written,
                    rows_purged,
                    compressed_bytes,
                    _SCHEMA_VERSION,
                    _canonical_json(run_payload),
                ),
            )
        return {
            "status": "COMPLETE",
            "objects_written": objects_written,
            "rows_purged": rows_purged,
            "compressed_bytes": compressed_bytes,
            "datasets": summaries,
        }
    finally:
        connection.execute(
            "SELECT pg_advisory_unlock(%s)",
            (_ARCHIVE_LOCK_KEY,),
        )
        connection.commit()


def restore_archive(
    connection: Any,
    store: ColdArchiveStore,
    *,
    archive_id: str,
) -> dict[str, Any]:
    """Restore one verified archive object into its original hot table."""

    manifest_row = connection.execute(
        """
        SELECT
            source_table,
            object_ref,
            object_checksum,
            row_count
        FROM cold_archive_manifests
        WHERE archive_id = %s
        """,
        (archive_id,),
    ).fetchone()
    connection.commit()
    if manifest_row is None:
        raise LookupError(archive_id)

    source_table = str(manifest_row[0])
    object_ref = str(manifest_row[1])
    checksum = str(manifest_row[2])
    expected_rows = int(manifest_row[3])
    allowed_tables = {
        policy.table for policy in archive_policies_from_env()
    }
    if source_table not in allowed_tables:
        raise RuntimeError("archive source table is not restore-allowlisted")

    started_at = datetime.now(UTC)
    inserted = 0
    with tempfile.TemporaryDirectory(prefix="baseball-restore-") as temp_dir:
        archive_path = Path(temp_dir) / "archive.jsonl.gz"
        store.download_file(ref=object_ref, path=archive_path)
        if sha256_file(archive_path) != checksum:
            raise RuntimeError("cold archive restore checksum mismatch")

        with gzip.open(archive_path, mode="rt", encoding="utf-8") as handle:
            records = [line.strip() for line in handle if line.strip()]

        if len(records) != expected_rows:
            raise RuntimeError(
                "cold archive restore row-count mismatch: "
                f"expected {expected_rows}, got {len(records)}"
            )

        target = sql.Identifier(source_table)
        insert_sql = sql.SQL(
            """
            INSERT INTO {table}
            SELECT *
            FROM jsonb_populate_record(NULL::{table}, %s::jsonb)
            ON CONFLICT DO NOTHING
            """
        ).format(table=target)

        with connection.transaction():
            for record in records:
                inserted += connection.execute(insert_sql, (record,)).rowcount

            finished_at = datetime.now(UTC)
            restore_id = str(
                uuid.uuid5(
                    _RESTORE_NAMESPACE,
                    f"{archive_id}:{finished_at.isoformat()}",
                )
            )
            payload = {
                "restore_id": restore_id,
                "archive_id": archive_id,
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "rows_inserted": inserted,
                "schema_version": _SCHEMA_VERSION,
            }
            connection.execute(
                """
                INSERT INTO cold_archive_restore_events (
                    restore_id,
                    archive_id,
                    started_at,
                    finished_at,
                    rows_inserted,
                    schema_version,
                    canonical_record
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    restore_id,
                    archive_id,
                    started_at,
                    finished_at,
                    inserted,
                    _SCHEMA_VERSION,
                    _canonical_json(payload),
                ),
            )

    return {
        "status": "COMPLETE",
        "archive_id": archive_id,
        "rows_expected": expected_rows,
        "rows_inserted": inserted,
    }
