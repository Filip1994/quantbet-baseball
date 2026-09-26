"""PostgreSQL persistence for versioned MLB identity evidence."""

from __future__ import annotations

import json
from typing import Any

from .mlb_identity import (
    MLBGameIdentityLink,
    MLBTeamIdentityMapping,
    canonical_game_identity_json,
    canonical_team_identity_json,
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


class PostgreSQLMLBIdentityRepository:
    def __init__(self, connection: ConnectionLike) -> None:
        self._connection = connection

    def _append(
        self,
        *,
        table: str,
        id_column: str,
        record_id: str,
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
                f"SELECT canonical_record FROM {table} WHERE {id_column} = %s",
                (record_id,),
            )
            row = cursor.fetchone()
        if row is None or _canonical_text(row[0]) != canonical:
            self._connection.rollback()
            raise EvidenceConflictError(
                f"conflicting immutable MLB identity: {record_id}"
            )
        self._connection.commit()
        return False

    def append_team_mapping(self, record: MLBTeamIdentityMapping) -> bool:
        canonical = canonical_team_identity_json(record)
        columns = (
            "mapping_id",
            "mapping_version",
            "api_sports_team_id",
            "api_sports_team_name",
            "official_mlb_team_id",
            "official_mlb_team_name",
            "verified_at",
            "api_fixture_observation_id",
            "api_source_payload_ref",
            "api_source_payload_checksum",
            "mlb_schedule_source_payload_ref",
            "mlb_schedule_source_payload_checksum",
            "schema_version",
            "canonical_record",
        )
        values = (
            record.mapping_id,
            record.mapping_version,
            record.api_sports_team_id,
            record.api_sports_team_name,
            record.official_mlb_team_id,
            record.official_mlb_team_name,
            record.verified_at,
            record.api_fixture_observation_id,
            record.api_source_payload_ref,
            record.api_source_payload_checksum,
            record.mlb_schedule_source_payload_ref,
            record.mlb_schedule_source_payload_checksum,
            record.schema_version,
            canonical,
        )
        return self._append(
            table="official_mlb_team_identity_mappings",
            id_column="mapping_id",
            record_id=record.mapping_id,
            columns=columns,
            values=values,
            canonical=canonical,
        )

    def append_game_link(self, record: MLBGameIdentityLink) -> bool:
        canonical = canonical_game_identity_json(record)
        columns = (
            "link_id",
            "mapping_version",
            "game_id",
            "api_sports_provider_game_id",
            "mlb_game_pk",
            "api_home_team_id",
            "api_away_team_id",
            "mlb_home_team_id",
            "mlb_away_team_id",
            "api_sports_first_pitch",
            "official_mlb_first_pitch",
            "kickoff_delta_seconds",
            "linked_at",
            "api_fixture_observation_id",
            "api_source_payload_ref",
            "api_source_payload_checksum",
            "mlb_schedule_source_payload_ref",
            "mlb_schedule_source_payload_checksum",
            "schema_version",
            "canonical_record",
        )
        values = (
            record.link_id,
            record.mapping_version,
            record.game_id,
            record.api_sports_provider_game_id,
            record.mlb_game_pk,
            record.api_home_team_id,
            record.api_away_team_id,
            record.mlb_home_team_id,
            record.mlb_away_team_id,
            record.api_sports_first_pitch,
            record.official_mlb_first_pitch,
            record.kickoff_delta_seconds,
            record.linked_at,
            record.api_fixture_observation_id,
            record.api_source_payload_ref,
            record.api_source_payload_checksum,
            record.mlb_schedule_source_payload_ref,
            record.mlb_schedule_source_payload_checksum,
            record.schema_version,
            canonical,
        )
        return self._append(
            table="official_mlb_game_identity_links",
            id_column="link_id",
            record_id=record.link_id,
            columns=columns,
            values=values,
            canonical=canonical,
        )

    def team_mappings(self, mapping_version: str) -> tuple[MLBTeamIdentityMapping, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record "
                "FROM official_mlb_team_identity_mappings "
                "WHERE mapping_version = %s ORDER BY api_sports_team_id",
                (mapping_version,),
            )
            rows = cursor.fetchall()
        result: list[MLBTeamIdentityMapping] = []
        for row in rows:
            value = row[0]
            if isinstance(value, str):
                value = json.loads(value)
            if isinstance(value, dict):
                result.append(MLBTeamIdentityMapping(**value))
        return tuple(result)
