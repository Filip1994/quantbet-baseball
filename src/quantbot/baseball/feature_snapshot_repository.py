"""PostgreSQL storage for immutable point-in-time model feature snapshots."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from .feature_snapshot import (
    FeatureSnapshot,
    FeatureSource,
    canonical_feature_snapshot_json,
)
from .postgres_repository import ConnectionLike, EvidenceConflictError


def _canonical_text(value: Any) -> str:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return value
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _as_of(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    return value.astimezone(UTC)


def _record(value: Any) -> FeatureSnapshot:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise EvidenceConflictError("feature snapshot canonical record is invalid")
    payload = dict(value)
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise EvidenceConflictError("feature snapshot sources are invalid")
    normalized_sources: list[FeatureSource] = []
    for source in sources:
        if not isinstance(source, dict):
            raise EvidenceConflictError("feature snapshot source is invalid")
        source_payload = dict(source)
        field_names = source_payload.get("field_names")
        if not isinstance(field_names, list):
            raise EvidenceConflictError("feature snapshot field_names are invalid")
        source_payload["field_names"] = tuple(field_names)
        normalized_sources.append(FeatureSource(**source_payload))
    payload["sources"] = tuple(normalized_sources)
    return FeatureSnapshot(**payload)


class PostgreSQLFeatureSnapshotRepository:
    def __init__(self, connection: ConnectionLike) -> None:
        self._connection = connection

    def append(self, snapshot: FeatureSnapshot) -> bool:
        canonical = canonical_feature_snapshot_json(snapshot)
        features = json.dumps(
            dict(snapshot.features),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        sources = json.dumps(
            [
                {
                    "source_name": source.source_name,
                    "observed_at": source.observed_at,
                    "retrieved_at": source.retrieved_at,
                    "source_payload_ref": source.source_payload_ref,
                    "source_payload_checksum": source.source_payload_checksum,
                    "field_names": list(source.field_names),
                }
                for source in snapshot.sources
            ],
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        null_reasons = json.dumps(
            dict(snapshot.null_reasons),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO feature_snapshots (
                    snapshot_id,
                    game_id,
                    feature_version,
                    generated_at,
                    source_data_cutoff_at,
                    kickoff_at,
                    schema_version,
                    features,
                    sources,
                    null_reasons,
                    canonical_record
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb
                )
                ON CONFLICT DO NOTHING
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.game_id,
                    snapshot.feature_version,
                    snapshot.generated_at,
                    snapshot.source_data_cutoff_at,
                    snapshot.kickoff_at,
                    snapshot.schema_version,
                    features,
                    sources,
                    null_reasons,
                    canonical,
                ),
            )
            if cursor.rowcount == 1:
                self._connection.commit()
                return True
            cursor.execute(
                "SELECT canonical_record FROM feature_snapshots WHERE snapshot_id = %s",
                (snapshot.snapshot_id,),
            )
            row = cursor.fetchone()

        if row is None or _canonical_text(row[0]) != canonical:
            self._connection.rollback()
            raise EvidenceConflictError(
                f"conflicting immutable feature snapshot: {snapshot.snapshot_id}"
            )
        self._connection.commit()
        return False

    def get(self, snapshot_id: str) -> FeatureSnapshot | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record FROM feature_snapshots WHERE snapshot_id = %s",
                (snapshot_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return _record(row[0])

    def latest_for_game_version(
        self,
        *,
        game_id: str,
        feature_version: str,
        as_of: datetime,
    ) -> FeatureSnapshot | None:
        cutoff = _as_of(as_of)
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT canonical_record
                FROM feature_snapshots
                WHERE game_id = %s
                  AND feature_version = %s
                  AND generated_at <= %s
                  AND source_data_cutoff_at <= %s
                ORDER BY
                    generated_at DESC,
                    source_data_cutoff_at DESC,
                    snapshot_id DESC
                LIMIT 1
                """,
                (game_id, feature_version, cutoff, cutoff),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return _record(row[0])

    def due_for_prediction(
        self,
        *,
        feature_versions: tuple[str, ...],
        as_of: datetime,
        horizon_minutes: int,
        limit: int,
    ) -> tuple[FeatureSnapshot, ...]:
        if not feature_versions:
            return ()
        if horizon_minutes < 1:
            raise ValueError("horizon_minutes must be positive")
        if limit < 1:
            raise ValueError("limit must be positive")
        cutoff = _as_of(as_of)
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT canonical_record
                FROM feature_snapshots
                WHERE feature_version = ANY(%s)
                  AND generated_at <= %s
                  AND source_data_cutoff_at <= %s
                  AND kickoff_at > %s
                  AND kickoff_at <= %s + (%s * INTERVAL '1 minute')
                ORDER BY kickoff_at, generated_at DESC, snapshot_id DESC
                LIMIT %s
                """,
                (
                    list(feature_versions),
                    cutoff,
                    cutoff,
                    cutoff,
                    cutoff,
                    horizon_minutes,
                    limit,
                ),
            )
            rows = cursor.fetchall()
        return tuple(_record(row[0]) for row in rows)

    def latest_for_game(
        self,
        *,
        game_id: str,
        as_of: datetime,
    ) -> FeatureSnapshot | None:
        cutoff = _as_of(as_of)
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT canonical_record
                FROM feature_snapshots
                WHERE game_id = %s
                  AND generated_at <= %s
                  AND source_data_cutoff_at <= %s
                ORDER BY
                    generated_at DESC,
                    source_data_cutoff_at DESC,
                    snapshot_id DESC
                LIMIT 1
                """,
                (game_id, cutoff, cutoff),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return _record(row[0])
