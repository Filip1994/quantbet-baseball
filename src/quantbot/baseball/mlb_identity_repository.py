"""PostgreSQL persistence for versioned MLB identity evidence."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from .fixture_evidence import FixtureObservation
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
        commit: bool = True,
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
                if commit:
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
        if commit:
            self._connection.commit()
        return False

    def _append_team_mapping(
        self,
        record: MLBTeamIdentityMapping,
        *,
        commit: bool,
    ) -> bool:
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
            commit=commit,
        )

    def append_team_mapping(self, record: MLBTeamIdentityMapping) -> bool:
        return self._append_team_mapping(record, commit=True)

    def append_team_mappings_atomically(
        self,
        records: tuple[MLBTeamIdentityMapping, ...],
    ) -> int:
        inserted = 0
        try:
            for record in records:
                if self._append_team_mapping(record, commit=False):
                    inserted += 1
        except Exception:
            self._connection.rollback()
            raise
        self._connection.commit()
        return inserted

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

    def latest_mlb_fixtures_for_provider_query_date(
        self,
        *,
        date_iso: str,
        observed_by: datetime,
    ) -> tuple[FixtureObservation, ...]:
        target = date.fromisoformat(date_iso)
        if observed_by.tzinfo is None or observed_by.utcoffset() is None:
            raise ValueError("observed_by must be timezone-aware")
        observed_cutoff = observed_by.astimezone(UTC)
        snapshot_query = """
            SELECT
                snapshot_group_id,
                source_payload_ref,
                source_payload_checksum
            FROM api_sports_game_schedule_snapshots
            WHERE query_date = %s
              AND observed_at <= %s
            ORDER BY observed_at DESC, snapshot_id DESC
            LIMIT 1
        """
        with self._connection.cursor() as cursor:
            cursor.execute(snapshot_query, (target, observed_cutoff))
            snapshot = cursor.fetchone()
        if snapshot is None:
            return ()

        snapshot_group_id, source_payload_ref, source_payload_checksum = snapshot
        query = """
            SELECT DISTINCT ON (fo.provider_game_id)
                fo.canonical_record
            FROM api_sports_game_schedule_snapshots AS schedule
            CROSS JOIN LATERAL unnest(schedule.provider_game_ids) AS member(provider_game_id)
            JOIN fixture_observations AS fo
              ON fo.provider_game_id = member.provider_game_id
             AND fo.source_payload_ref = schedule.source_payload_ref
             AND fo.source_payload_checksum = schedule.source_payload_checksum
            WHERE schedule.snapshot_group_id = %s
              AND schedule.query_date = %s
              AND schedule.source_payload_ref = %s
              AND schedule.source_payload_checksum = %s
              AND lower(fo.league) = 'mlb'
              AND fo.observed_at <= %s
            ORDER BY fo.provider_game_id, fo.observed_at DESC, fo.fixture_observation_id DESC
        """
        with self._connection.cursor() as cursor:
            cursor.execute(
                query,
                (
                    snapshot_group_id,
                    target,
                    source_payload_ref,
                    source_payload_checksum,
                    observed_cutoff,
                ),
            )
            rows = cursor.fetchall()

        fixtures: list[FixtureObservation] = []
        for row in rows:
            value = row[0]
            if isinstance(value, str):
                value = json.loads(value)
            if isinstance(value, dict):
                fixtures.append(FixtureObservation(**value))
        return tuple(
            sorted(
                fixtures,
                key=lambda item: (item.kickoff_at, item.provider_game_id),
            )
        )

    def latest_mlb_fixtures_for_schedule_date(
        self,
        *,
        date_iso: str,
        observed_by: datetime,
    ) -> tuple[FixtureObservation, ...]:
        target = date.fromisoformat(date_iso)
        if observed_by.tzinfo is None or observed_by.utcoffset() is None:
            raise ValueError("observed_by must be timezone-aware")

        # API-Sports collection fetches UTC calendar dates independently. One
        # North-American MLB slate spans 06:00Z -> 06:00Z, so identity needs a
        # coherent pair of provider date snapshots. Use only the newest group
        # for which both dates were durably archived. This prevents a fixture
        # removed from a later provider schedule from surviving forever merely
        # because an older fixture observation still exists.
        first_query_date = target
        second_query_date = target + timedelta(days=1)
        observed_cutoff = observed_by.astimezone(UTC)
        group_query = """
            SELECT snapshot_group_id
            FROM api_sports_game_schedule_snapshots
            WHERE query_date IN (%s, %s)
              AND observed_at <= %s
            GROUP BY snapshot_group_id
            HAVING COUNT(DISTINCT query_date) = 2
            ORDER BY MAX(observed_at) DESC, snapshot_group_id DESC
            LIMIT 1
        """
        with self._connection.cursor() as cursor:
            cursor.execute(
                group_query,
                (first_query_date, second_query_date, observed_cutoff),
            )
            group_row = cursor.fetchone()
        if group_row is None:
            return ()

        snapshot_group_id = group_row[0]
        start = datetime.combine(target, time(6), tzinfo=UTC)
        end = datetime.combine(target + timedelta(days=1), time(6), tzinfo=UTC)
        query = """
            SELECT DISTINCT ON (fo.provider_game_id)
                fo.canonical_record
            FROM api_sports_game_schedule_snapshots AS snapshot
            CROSS JOIN LATERAL unnest(snapshot.provider_game_ids) AS member(provider_game_id)
            JOIN fixture_observations AS fo
              ON fo.provider_game_id = member.provider_game_id
             AND fo.source_payload_ref = snapshot.source_payload_ref
             AND fo.source_payload_checksum = snapshot.source_payload_checksum
            WHERE snapshot.snapshot_group_id = %s
              AND snapshot.query_date IN (%s, %s)
              AND lower(fo.league) = 'mlb'
              AND fo.kickoff_at >= %s
              AND fo.kickoff_at < %s
              AND fo.observed_at <= %s
            ORDER BY fo.provider_game_id, fo.observed_at DESC, fo.fixture_observation_id DESC
        """
        with self._connection.cursor() as cursor:
            cursor.execute(
                query,
                (
                    snapshot_group_id,
                    first_query_date,
                    second_query_date,
                    start,
                    end,
                    observed_cutoff,
                ),
            )
            rows = cursor.fetchall()
        fixtures: list[FixtureObservation] = []
        for row in rows:
            value = row[0]
            if isinstance(value, str):
                value = json.loads(value)
            if isinstance(value, dict):
                fixtures.append(FixtureObservation(**value))
        return tuple(
            sorted(
                fixtures,
                key=lambda item: (item.kickoff_at, item.provider_game_id),
            )
        )

    def game_links(
        self,
        mapping_version: str,
    ) -> tuple[MLBGameIdentityLink, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record FROM official_mlb_game_identity_links "
                "WHERE mapping_version = %s "
                "ORDER BY official_mlb_first_pitch, api_sports_provider_game_id",
                (mapping_version,),
            )
            rows = cursor.fetchall()
        result: list[MLBGameIdentityLink] = []
        for row in rows:
            value = row[0]
            if isinstance(value, str):
                value = json.loads(value)
            if isinstance(value, dict):
                result.append(MLBGameIdentityLink(**value))
        return tuple(result)

    def game_link_for_provider_game(
        self,
        *,
        mapping_version: str,
        provider_game_id: int,
    ) -> MLBGameIdentityLink | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record FROM official_mlb_game_identity_links "
                "WHERE mapping_version = %s AND api_sports_provider_game_id = %s",
                (mapping_version, provider_game_id),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        value = row[0]
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict):
            return None
        return MLBGameIdentityLink(**value)
