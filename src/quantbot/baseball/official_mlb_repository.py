"""PostgreSQL storage for immutable official MLB pregame evidence."""

from __future__ import annotations

import json
from typing import Any

from .official_mlb import (
    OfficialMLBPregameSnapshot,
    canonical_pregame_snapshot_json,
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


class PostgreSQLOfficialMLBRepository:
    def __init__(self, connection: ConnectionLike) -> None:
        self._connection = connection

    def append_snapshot(self, record: OfficialMLBPregameSnapshot) -> bool:
        canonical = canonical_pregame_snapshot_json(record)
        values = (
            record.snapshot_id,
            record.mlb_game_pk,
            record.provider,
            record.source_observed_at,
            record.retrieved_at,
            record.scheduled_first_pitch,
            record.requested_timecode,
            record.status_abstract,
            record.status_detailed,
            record.away_team_id,
            record.home_team_id,
            record.away_probable_pitcher_id,
            record.home_probable_pitcher_id,
            len(record.away_batting_order_ids),
            len(record.home_batting_order_ids),
            record.lineup_state,
            record.venue_id,
            record.source_payload_ref,
            record.source_payload_checksum,
            record.schema_version,
            canonical,
        )
        columns = (
            "snapshot_id",
            "mlb_game_pk",
            "provider",
            "source_observed_at",
            "retrieved_at",
            "scheduled_first_pitch",
            "requested_timecode",
            "status_abstract",
            "status_detailed",
            "away_team_id",
            "home_team_id",
            "away_probable_pitcher_id",
            "home_probable_pitcher_id",
            "away_lineup_count",
            "home_lineup_count",
            "lineup_state",
            "venue_id",
            "source_payload_ref",
            "source_payload_checksum",
            "schema_version",
            "canonical_record",
        )
        placeholders = ["%s"] * len(values)
        placeholders[-1] = "%s::jsonb"
        insert = (
            f"INSERT INTO official_mlb_pregame_snapshots ({', '.join(columns)}) "
            f"VALUES ({', '.join(placeholders)}) ON CONFLICT DO NOTHING"
        )
        with self._connection.cursor() as cursor:
            cursor.execute(insert, values)
            if cursor.rowcount == 1:
                self._connection.commit()
                return True
            cursor.execute(
                "SELECT canonical_record FROM official_mlb_pregame_snapshots "
                "WHERE snapshot_id = %s",
                (record.snapshot_id,),
            )
            existing = cursor.fetchone()
        if existing is None or _canonical_text(existing[0]) != canonical:
            self._connection.rollback()
            raise EvidenceConflictError(
                f"conflicting official MLB snapshot identity: {record.snapshot_id}"
            )
        self._connection.commit()
        return False
