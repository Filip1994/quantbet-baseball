"""Verified cold-storage tiering for append-only Baseball evidence.

The production PostgreSQL database remains the hot operational store. Only rows
that are no longer needed by live decisioning are eligible for archival. Every
purge is preceded by a deterministic gzip archive written to the existing
S3-compatible Baseball bucket and verified with a SHA-256 checksum.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import boto3
import psycopg
from botocore.config import Config

from .db import apply_migrations, database_url_from_env

_ARCHIVE_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/cold-storage/v1",
)

_ALLOWED_TABLES = {
    "api_sports_game_history_snapshots",
    "fixture_observations",
    "odds_observations",
    "odds_poll_attempts",
}


@dataclass(frozen=True, slots=True)
class ColdArchivePolicy:
    table_name: str
    primary_key: str
    time_column: str
    archive_mode: str
    retention: timedelta

    def __post_init__(self) -> None:
        if self.table_name not in _ALLOWED_TABLES:
            raise ValueError("unsupported cold-storage table")
        if self.retention <= timedelta(0):
            raise ValueError("cold-storage retention must be positive")


@dataclass(frozen=True, slots=True)
class ColdArchiveRow:
    primary_key: str
    record_at: datetime
    record: dict[str, Any]


@dataclass(frozen=True, slots=True)
class VerifiedColdObject:
    ref: str
    checksum: str
    size_bytes: int


class ColdObjectStore(Protocol):
    def put_verified(
        self,
        *,
        key: str,
        body: bytes,
        checksum: str,
    ) -> VerifiedColdObject: ...

    def get_verified(self, ref: str, checksum: str) -> bytes: ...


class S3ColdObjectStore:
    def __init__(self, *, client: Any, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    def put_verified(
        self,
        *,
        key: str,
        body: bytes,
        checksum: str,
    ) -> VerifiedColdObject:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
            ContentEncoding="gzip",
            Metadata={"sha256": checksum},
        )
        head = self.client.head_object(Bucket=self.bucket, Key=key)
        stored_size = int(head.get("ContentLength") or 0)
        stored_checksum = str((head.get("Metadata") or {}).get("sha256") or "")
        if stored_size != len(body) or stored_checksum != checksum:
            raise RuntimeError("cold object verification failed after upload")
        return VerifiedColdObject(
            ref=f"s3://{self.bucket}/{key}",
            checksum=checksum,
            size_bytes=stored_size,
        )

    def get_verified(self, ref: str, checksum: str) -> bytes:
        prefix = f"s3://{self.bucket}/"
        if not ref.startswith(prefix):
            raise ValueError("cold object ref belongs to a different bucket")
        key = ref[len(prefix) :]
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        body = response["Body"].read()
        actual = hashlib.sha256(body).hexdigest()
        if actual != checksum:
            raise RuntimeError("cold object checksum verification failed")
        return body


def cold_object_store_from_env() -> S3ColdObjectStore:
    names = (
        "BASEBALL_RAW_BUCKET",
        "BASEBALL_RAW_REGION",
        "BASEBALL_RAW_ENDPOINT",
        "BASEBALL_RAW_ACCESS_KEY_ID",
        "BASEBALL_RAW_SECRET_ACCESS_KEY",
    )
    values = {name: os.getenv(name, "").strip() for name in names}
    missing = sorted(name for name, value in values.items() if not value)
    if missing:
        raise RuntimeError(
            "cold storage requires the existing Baseball raw bucket: "
            + ", ".join(missing)
        )
    client = boto3.client(
        "s3",
        endpoint_url=values["BASEBALL_RAW_ENDPOINT"],
        aws_access_key_id=values["BASEBALL_RAW_ACCESS_KEY_ID"],
        aws_secret_access_key=values["BASEBALL_RAW_SECRET_ACCESS_KEY"],
        region_name=values["BASEBALL_RAW_REGION"],
        config=Config(s3={"addressing_style": "virtual"}),
    )
    return S3ColdObjectStore(
        client=client,
        bucket=values["BASEBALL_RAW_BUCKET"],
    )


def _policy_days(env_name: str, default: int) -> int:
    value = int(os.getenv(env_name, str(default)))
    if value < 1:
        raise ValueError(f"{env_name} must be positive")
    return value


def policies_from_env() -> tuple[ColdArchivePolicy, ...]:
    return (
        ColdArchivePolicy(
            table_name="api_sports_game_history_snapshots",
            primary_key="snapshot_id",
            time_column="observed_at",
            archive_mode="SUPERSEDED",
            retention=timedelta(
                days=_policy_days(
                    "BASEBALL_COLD_GAME_HISTORY_SUPERSEDED_DAYS",
                    2,
                )
            ),
        ),
        ColdArchivePolicy(
            table_name="fixture_observations",
            primary_key="fixture_observation_id",
            time_column="observed_at",
            archive_mode="SUPERSEDED_UNREFERENCED",
            retention=timedelta(
                days=_policy_days(
                    "BASEBALL_COLD_FIXTURE_SUPERSEDED_DAYS",
                    7,
                )
            ),
        ),
        ColdArchivePolicy(
            table_name="odds_observations",
            primary_key="observation_id",
            time_column="observed_at",
            archive_mode="UNREFERENCED",
            retention=timedelta(
                days=_policy_days(
                    "BASEBALL_COLD_ODDS_UNREFERENCED_DAYS",
                    7,
                )
            ),
        ),
        ColdArchivePolicy(
            table_name="odds_poll_attempts",
            primary_key="poll_attempt_id",
            time_column="attempted_at",
            archive_mode="AGE",
            retention=timedelta(
                days=_policy_days(
                    "BASEBALL_COLD_POLL_ATTEMPT_DAYS",
                    7,
                )
            ),
        ),
    )


def _select_sql(policy: ColdArchivePolicy) -> str:
    if policy.table_name == "api_sports_game_history_snapshots":
        return """
            SELECT
                old.snapshot_id::text AS primary_key,
                old.observed_at AS record_at,
                row_to_json(old) AS record
            FROM api_sports_game_history_snapshots AS old
            WHERE old.observed_at < %s
              AND EXISTS (
                  SELECT 1
                  FROM api_sports_game_history_snapshots AS newer
                  WHERE newer.provider_game_id = old.provider_game_id
                    AND (
                        newer.observed_at > old.observed_at
                        OR (
                            newer.observed_at = old.observed_at
                            AND newer.snapshot_id > old.snapshot_id
                        )
                    )
              )
            ORDER BY old.observed_at, old.snapshot_id
            LIMIT %s
        """
    if policy.table_name == "fixture_observations":
        return """
            SELECT
                old.fixture_observation_id::text AS primary_key,
                old.observed_at AS record_at,
                row_to_json(old) AS record
            FROM fixture_observations AS old
            WHERE old.observed_at < %s
              AND EXISTS (
                  SELECT 1
                  FROM fixture_observations AS newer
                  WHERE newer.provider_game_id = old.provider_game_id
                    AND (
                        newer.observed_at > old.observed_at
                        OR (
                            newer.observed_at = old.observed_at
                            AND newer.fixture_observation_id > old.fixture_observation_id
                        )
                    )
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM pick_closing_finalizations AS closing
                  WHERE closing.fixture_observation_id = old.fixture_observation_id
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM game_result_facts AS result
                  WHERE result.fixture_observation_id = old.fixture_observation_id
              )
            ORDER BY old.observed_at, old.fixture_observation_id
            LIMIT %s
        """
    if policy.table_name == "odds_observations":
        return """
            SELECT
                old.observation_id::text AS primary_key,
                old.observed_at AS record_at,
                row_to_json(old) AS record
            FROM odds_observations AS old
            WHERE old.observed_at < %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM value_evaluations AS evaluation
                  WHERE old.observation_id IN (
                      evaluation.home_observation_id,
                      evaluation.away_observation_id,
                      evaluation.selected_observation_id
                  )
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM pick_closing_finalizations AS closing
                  WHERE old.observation_id IN (
                      closing.candidate_home_observation_id,
                      closing.candidate_away_observation_id,
                      closing.closing_observation_id
                  )
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM pick_settlements AS settlement
                  WHERE settlement.closing_observation_id = old.observation_id
              )
            ORDER BY old.observed_at, old.observation_id
            LIMIT %s
        """
    if policy.table_name == "odds_poll_attempts":
        return """
            SELECT
                old.poll_attempt_id::text AS primary_key,
                old.attempted_at AS record_at,
                row_to_json(old) AS record
            FROM odds_poll_attempts AS old
            WHERE old.attempted_at < %s
            ORDER BY old.attempted_at, old.poll_attempt_id
            LIMIT %s
        """
    raise ValueError("unsupported cold-storage policy")


def select_eligible_rows(
    connection: Any,
    policy: ColdArchivePolicy,
    *,
    cutoff: datetime,
    limit: int,
) -> tuple[ColdArchiveRow, ...]:
    if limit < 1:
        raise ValueError("cold-storage row limit must be positive")
    with connection.cursor() as cursor:
        cursor.execute(_select_sql(policy), (cutoff, limit))
        rows = cursor.fetchall()
    result: list[ColdArchiveRow] = []
    for primary_key, record_at, record in rows:
        if not isinstance(record, dict):
            raise RuntimeError("row_to_json did not return an object")
        result.append(
            ColdArchiveRow(
                primary_key=str(primary_key),
                record_at=record_at.astimezone(UTC),
                record=record,
            )
        )
    return tuple(result)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    raise TypeError(f"unsupported cold-storage JSON type: {type(value)!r}")


def build_archive_body(
    policy: ColdArchivePolicy,
    *,
    cutoff: datetime,
    rows: tuple[ColdArchiveRow, ...],
) -> tuple[bytes, str, str]:
    if not rows:
        raise ValueError("cannot build an empty cold archive")
    payload = {
        "schema_version": "1.0",
        "table_name": policy.table_name,
        "archive_mode": policy.archive_mode,
        "cutoff_at": cutoff.astimezone(UTC).isoformat(),
        "row_count": len(rows),
        "rows": [row.record for row in rows],
    }
    raw = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    body = gzip.compress(raw, compresslevel=9, mtime=0)
    checksum = hashlib.sha256(body).hexdigest()
    archive_id = str(
        uuid.uuid5(
            _ARCHIVE_NAMESPACE,
            f"{policy.table_name}:{policy.archive_mode}:{checksum}",
        )
    )
    return body, checksum, archive_id


def _object_key(
    *,
    prefix: str,
    policy: ColdArchivePolicy,
    archived_at: datetime,
    archive_id: str,
) -> str:
    safe_prefix = prefix.strip("/") or "cold/baseball"
    day = archived_at.astimezone(UTC).strftime("%Y-%m-%d")
    return (
        f"{safe_prefix}/{policy.table_name}/{day}/"
        f"{archive_id}.json.gz"
    )


def _manifest_record(
    *,
    archive_id: str,
    policy: ColdArchivePolicy,
    cutoff: datetime,
    verified: VerifiedColdObject,
    rows: tuple[ColdArchiveRow, ...],
    archived_at: datetime,
) -> dict[str, Any]:
    return {
        "archive_id": archive_id,
        "table_name": policy.table_name,
        "archive_mode": policy.archive_mode,
        "cutoff_at": cutoff.astimezone(UTC).isoformat(),
        "object_ref": verified.ref,
        "object_sha256": verified.checksum,
        "object_bytes": verified.size_bytes,
        "row_count": len(rows),
        "first_record_at": min(row.record_at for row in rows).isoformat(),
        "last_record_at": max(row.record_at for row in rows).isoformat(),
        "archived_at": archived_at.astimezone(UTC).isoformat(),
        "purged_from_hot_at": archived_at.astimezone(UTC).isoformat(),
        "schema_version": "1.0",
    }


def purge_verified_rows(
    connection: Any,
    policy: ColdArchivePolicy,
    *,
    rows: tuple[ColdArchiveRow, ...],
    archive_id: str,
    cutoff: datetime,
    verified: VerifiedColdObject,
    archived_at: datetime,
) -> int:
    if not rows:
        return 0
    ids = [row.primary_key for row in rows]
    manifest = _manifest_record(
        archive_id=archive_id,
        policy=policy,
        cutoff=cutoff,
        verified=verified,
        rows=rows,
        archived_at=archived_at,
    )
    canonical = json.dumps(
        manifest,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    table = policy.table_name
    primary_key = policy.primary_key
    if table not in _ALLOWED_TABLES:
        raise ValueError("unsupported cold-storage table")
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute(
                f'DELETE FROM "{table}" '
                f'WHERE "{primary_key}" = ANY(%s::uuid[])',
                (ids,),
            )
            deleted = int(cursor.rowcount)
            if deleted != len(ids):
                raise RuntimeError(
                    f"cold purge row mismatch for {table}: "
                    f"expected {len(ids)}, deleted {deleted}"
                )
            cursor.execute(
                """
                INSERT INTO cold_storage_archives (
                    archive_id,
                    table_name,
                    archive_mode,
                    cutoff_at,
                    object_ref,
                    object_sha256,
                    object_bytes,
                    row_count,
                    first_record_at,
                    last_record_at,
                    archived_at,
                    purged_from_hot_at,
                    schema_version,
                    canonical_record
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s::jsonb
                )
                """,
                (
                    archive_id,
                    policy.table_name,
                    policy.archive_mode,
                    cutoff,
                    verified.ref,
                    verified.checksum,
                    verified.size_bytes,
                    len(rows),
                    min(row.record_at for row in rows),
                    max(row.record_at for row in rows),
                    archived_at,
                    archived_at,
                    "1.0",
                    canonical,
                ),
            )
    return len(ids)


def restore_archive(
    connection: Any,
    object_store: ColdObjectStore,
    *,
    archive_id: str,
) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name, object_ref, object_sha256
            FROM cold_storage_archives
            WHERE archive_id = %s
            """,
            (archive_id,),
        )
        row = cursor.fetchone()
    if row is None:
        raise LookupError(f"unknown cold archive: {archive_id}")
    table_name, object_ref, checksum = row
    if table_name not in _ALLOWED_TABLES:
        raise RuntimeError("archive manifest references an unsupported table")
    compressed = object_store.get_verified(str(object_ref), str(checksum))
    payload = json.loads(gzip.decompress(compressed))
    if payload.get("table_name") != table_name:
        raise RuntimeError("cold archive table identity mismatch")
    records = payload.get("rows")
    if not isinstance(records, list):
        raise RuntimeError("cold archive rows are invalid")
    inserted = 0
    with connection.transaction():
        with connection.cursor() as cursor:
            for record in records:
                before = cursor.rowcount
                cursor.execute(
                    f'INSERT INTO "{table_name}" '
                    f'SELECT * FROM json_populate_record(NULL::"{table_name}", %s::json) '
                    "ON CONFLICT DO NOTHING",
                    (json.dumps(record, separators=(",", ":")),),
                )
                if cursor.rowcount > 0 and cursor.rowcount != before:
                    inserted += int(cursor.rowcount)
    return inserted


def run_cold_storage_cycle(
    connection: Any,
    object_store: ColdObjectStore,
    *,
    now: datetime,
    policies: tuple[ColdArchivePolicy, ...],
    max_rows_per_table: int,
    purge_enabled: bool,
    prefix: str = "cold/baseball",
) -> dict[str, Any]:
    current = now.astimezone(UTC)
    summary: dict[str, Any] = {
        "status": "DRY_RUN" if not purge_enabled else "COMPLETE",
        "checked_at": current.isoformat(),
        "purge_enabled": purge_enabled,
        "max_rows_per_table": max_rows_per_table,
        "tables": {},
        "rows_archived": 0,
        "bytes_archived": 0,
    }
    for policy in policies:
        cutoff = current - policy.retention
        rows = select_eligible_rows(
            connection,
            policy,
            cutoff=cutoff,
            limit=max_rows_per_table,
        )
        table_summary: dict[str, Any] = {
            "archive_mode": policy.archive_mode,
            "retention_days": policy.retention.days,
            "eligible_rows": len(rows),
            "archived_rows": 0,
            "archived_bytes": 0,
        }
        if rows and purge_enabled:
            body, checksum, archive_id = build_archive_body(
                policy,
                cutoff=cutoff,
                rows=rows,
            )
            key = _object_key(
                prefix=prefix,
                policy=policy,
                archived_at=current,
                archive_id=archive_id,
            )
            verified = object_store.put_verified(
                key=key,
                body=body,
                checksum=checksum,
            )
            purged = purge_verified_rows(
                connection,
                policy,
                rows=rows,
                archive_id=archive_id,
                cutoff=cutoff,
                verified=verified,
                archived_at=current,
            )
            table_summary["archived_rows"] = purged
            table_summary["archived_bytes"] = verified.size_bytes
            table_summary["object_ref"] = verified.ref
            summary["rows_archived"] += purged
            summary["bytes_archived"] += verified.size_bytes
        summary["tables"][policy.table_name] = table_summary
    return summary


def _enabled(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def main() -> None:
    if not _enabled("BASEBALL_COLD_STORAGE_ENABLED"):
        print(json.dumps({"status": "DISABLED"}, sort_keys=True))
        return

    root = Path.cwd()
    database_url = database_url_from_env()
    apply_migrations(root, database_url)
    max_rows = int(os.getenv("BASEBALL_COLD_MAX_ROWS_PER_TABLE", "5000"))
    if max_rows < 1 or max_rows > 20000:
        raise ValueError("BASEBALL_COLD_MAX_ROWS_PER_TABLE must be between 1 and 20000")
    purge_enabled = _enabled("BASEBALL_COLD_PURGE_ENABLED")
    prefix = os.getenv("BASEBALL_COLD_PREFIX", "cold/baseball").strip()
    store = cold_object_store_from_env()
    with psycopg.connect(database_url) as connection:
        summary = run_cold_storage_cycle(
            connection,
            store,
            now=datetime.now(UTC),
            policies=policies_from_env(),
            max_rows_per_table=max_rows,
            purge_enabled=purge_enabled,
            prefix=prefix,
        )
        if purge_enabled:
            for table_name, table_summary in summary["tables"].items():
                if int(table_summary["archived_rows"]) <= 0:
                    continue
                connection.commit()
                connection.autocommit = True
                connection.execute(f'VACUUM (ANALYZE) "{table_name}"')
                connection.autocommit = False
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
