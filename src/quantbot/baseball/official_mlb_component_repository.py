"""PostgreSQL storage/query boundary for Official MLB pregame components."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from .official_mlb_components import (
    OfficialMLBLineupEvidence,
    OfficialMLBStarterEvidence,
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
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


class PostgreSQLOfficialMLBComponentRepository:
    def __init__(self, connection: ConnectionLike) -> None:
        self._connection = connection

    def _append(
        self,
        *,
        table: str,
        evidence_id: str,
        columns: tuple[str, ...],
        values: tuple[Any, ...],
        canonical: str,
    ) -> bool:
        placeholders = ["%s"] * len(values)
        placeholders[-1] = "%s::jsonb"
        query = (
            f"INSERT INTO {table} ({', '.join(columns)}) "
            f"VALUES ({', '.join(placeholders)}) ON CONFLICT DO NOTHING"
        )
        with self._connection.cursor() as cursor:
            cursor.execute(query, values)
            if cursor.rowcount == 1:
                self._connection.commit()
                return True
            cursor.execute(
                f"SELECT canonical_record FROM {table} WHERE evidence_id = %s",
                (evidence_id,),
            )
            row = cursor.fetchone()
        if row is None or _canonical_text(row[0]) != canonical:
            self._connection.rollback()
            raise EvidenceConflictError(
                f"conflicting Official MLB component evidence: {evidence_id}"
            )
        self._connection.commit()
        return False

    def append_starter(self, record: OfficialMLBStarterEvidence) -> bool:
        canonical = canonical_component_json(record)
        columns = (
            "evidence_id",
            "mlb_game_pk",
            "side",
            "starter_state",
            "pitcher_id",
            "pitcher_name",
            "source_observed_at",
            "retrieved_at",
            "scheduled_first_pitch",
            "requested_timecode",
            "source_payload_ref",
            "source_payload_checksum",
            "schema_version",
            "canonical_record",
        )
        values = (
            record.evidence_id,
            record.mlb_game_pk,
            record.side,
            record.starter_state,
            record.pitcher_id,
            record.pitcher_name,
            record.source_observed_at,
            record.retrieved_at,
            record.scheduled_first_pitch,
            record.requested_timecode,
            record.source_payload_ref,
            record.source_payload_checksum,
            record.schema_version,
            canonical,
        )
        return self._append(
            table="official_mlb_starter_evidence",
            evidence_id=record.evidence_id,
            columns=columns,
            values=values,
            canonical=canonical,
        )

    def append_lineup(self, record: OfficialMLBLineupEvidence) -> bool:
        canonical = canonical_component_json(record)
        columns = (
            "evidence_id",
            "mlb_game_pk",
            "side",
            "lineup_state",
            "batting_order_ids",
            "confirmation_state",
            "source_observed_at",
            "retrieved_at",
            "scheduled_first_pitch",
            "requested_timecode",
            "source_payload_ref",
            "source_payload_checksum",
            "schema_version",
            "canonical_record",
        )
        values = (
            record.evidence_id,
            record.mlb_game_pk,
            record.side,
            record.lineup_state,
            list(record.batting_order_ids),
            record.confirmation_state,
            record.source_observed_at,
            record.retrieved_at,
            record.scheduled_first_pitch,
            record.requested_timecode,
            record.source_payload_ref,
            record.source_payload_checksum,
            record.schema_version,
            canonical,
        )
        return self._append(
            table="official_mlb_lineup_evidence",
            evidence_id=record.evidence_id,
            columns=columns,
            values=values,
            canonical=canonical,
        )

    def latest_starter_known_at(
        self,
        *,
        mlb_game_pk: int,
        side: str,
        as_of: datetime,
    ) -> OfficialMLBStarterEvidence | None:
        cutoff = _utc(as_of, "as_of")
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT canonical_record
                FROM official_mlb_starter_evidence
                WHERE mlb_game_pk = %s
                  AND side = %s
                  AND source_observed_at <= %s
                  AND retrieved_at <= %s
                  AND scheduled_first_pitch > %s
                ORDER BY source_observed_at DESC, retrieved_at DESC, evidence_id DESC
                LIMIT 1
                """,
                (mlb_game_pk, side, cutoff, cutoff, cutoff),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        value = row[0]
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict):
            return None
        return OfficialMLBStarterEvidence(**value)

    def latest_lineup_known_at(
        self,
        *,
        mlb_game_pk: int,
        side: str,
        as_of: datetime,
    ) -> OfficialMLBLineupEvidence | None:
        cutoff = _utc(as_of, "as_of")
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT canonical_record
                FROM official_mlb_lineup_evidence
                WHERE mlb_game_pk = %s
                  AND side = %s
                  AND source_observed_at <= %s
                  AND retrieved_at <= %s
                  AND scheduled_first_pitch > %s
                ORDER BY source_observed_at DESC, retrieved_at DESC, evidence_id DESC
                LIMIT 1
                """,
                (mlb_game_pk, side, cutoff, cutoff, cutoff),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        value = row[0]
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict):
            return None
        value["batting_order_ids"] = tuple(value.get("batting_order_ids") or ())
        return OfficialMLBLineupEvidence(**value)
