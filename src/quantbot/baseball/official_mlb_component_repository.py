"""PostgreSQL storage for component-level Official MLB pregame evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from .official_mlb_components import (
    OfficialMLBPregameComponent,
    canonical_component_json,
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
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _record(value: Any) -> OfficialMLBPregameComponent:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise EvidenceConflictError(
            "official MLB component canonical record is invalid"
        )
    return OfficialMLBPregameComponent(**value)


def _as_of(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    return value.astimezone(UTC)


class PostgreSQLOfficialMLBComponentRepository:
    def __init__(self, connection: ConnectionLike) -> None:
        self._connection = connection

    def _append(
        self,
        record: OfficialMLBPregameComponent,
        *,
        commit: bool,
    ) -> bool:
        canonical = canonical_component_json(record)
        values = (
            record.component_id,
            record.mlb_game_pk,
            record.provider,
            record.component_type,
            record.side,
            record.state,
            record.source_observed_at,
            record.retrieved_at,
            record.scheduled_first_pitch,
            record.requested_timecode,
            record.source_payload_ref,
            record.source_payload_checksum,
            record.schema_version,
            canonical,
        )
        columns = (
            "component_id",
            "mlb_game_pk",
            "provider",
            "component_type",
            "side",
            "state",
            "source_observed_at",
            "retrieved_at",
            "scheduled_first_pitch",
            "requested_timecode",
            "source_payload_ref",
            "source_payload_checksum",
            "schema_version",
            "canonical_record",
        )
        placeholders = ["%s"] * len(values)
        placeholders[-1] = "%s::jsonb"
        insert = (
            "INSERT INTO official_mlb_pregame_components "
            f"({', '.join(columns)}) VALUES ({', '.join(placeholders)}) "
            "ON CONFLICT DO NOTHING"
        )
        with self._connection.cursor() as cursor:
            cursor.execute(insert, values)
            if cursor.rowcount == 1:
                if commit:
                    self._connection.commit()
                return True
            cursor.execute(
                "SELECT canonical_record FROM official_mlb_pregame_components "
                "WHERE component_id = %s",
                (record.component_id,),
            )
            existing = cursor.fetchone()
        if existing is None or _canonical_text(existing[0]) != canonical:
            self._connection.rollback()
            raise EvidenceConflictError(
                f"conflicting official MLB component identity: {record.component_id}"
            )
        if commit:
            self._connection.commit()
        return False

    def append_components(
        self,
        records: tuple[OfficialMLBPregameComponent, ...],
    ) -> int:
        inserted = 0
        try:
            for record in records:
                if self._append(record, commit=False):
                    inserted += 1
        except Exception:
            self._connection.rollback()
            raise
        self._connection.commit()
        return inserted

    def latest_component(
        self,
        *,
        mlb_game_pk: int,
        component_type: str,
        side: str,
        as_of: datetime,
    ) -> OfficialMLBPregameComponent | None:
        cutoff = _as_of(as_of)
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT canonical_record
                FROM official_mlb_pregame_components
                WHERE mlb_game_pk = %s
                  AND component_type = %s
                  AND side = %s
                  AND source_observed_at <= %s
                ORDER BY source_observed_at DESC, component_id DESC
                LIMIT 1
                """,
                (mlb_game_pk, component_type, side, cutoff),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return _record(row[0])

    def latest_components_for_game(
        self,
        *,
        mlb_game_pk: int,
        as_of: datetime,
    ) -> tuple[OfficialMLBPregameComponent, ...]:
        cutoff = _as_of(as_of)
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT ON (component_type, side)
                    canonical_record
                FROM official_mlb_pregame_components
                WHERE mlb_game_pk = %s
                  AND source_observed_at <= %s
                ORDER BY
                    component_type,
                    side,
                    source_observed_at DESC,
                    component_id DESC
                """,
                (mlb_game_pk, cutoff),
            )
            rows = cursor.fetchall()
        result = tuple(_record(row[0]) for row in rows)
        return tuple(
            sorted(
                result,
                key=lambda item: (item.component_type, item.side),
            )
        )
