"""PostgreSQL storage for slow-moving API-Sports primary-provider evidence."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from .postgres_repository import ConnectionLike, EvidenceConflictError
from .provider_data import (
    ReferenceCatalogSnapshot,
    StandingSnapshot,
    TeamStatisticsSnapshot,
    canonical_json,
)


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


class PostgreSQLProviderDataRepository:
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
                f"conflicting immutable provider-data identity: {record_id}"
            )
        self._connection.commit()
        return False

    def append_standings(self, records: Iterable[StandingSnapshot]) -> int:
        inserted = 0
        for record in records:
            canonical = canonical_json(record)
            columns = (
                "snapshot_id",
                "provider",
                "league_id",
                "season",
                "team_id",
                "team_name",
                "observed_at",
                "games_played",
                "wins",
                "losses",
                "win_percentage",
                "loss_percentage",
                "runs_for",
                "runs_against",
                "position",
                "stage",
                "group_name",
                "source_payload_ref",
                "source_payload_checksum",
                "schema_version",
                "canonical_record",
            )
            values = (
                record.snapshot_id,
                record.provider,
                record.league_id,
                record.season,
                record.team_id,
                record.team_name,
                record.observed_at,
                record.games_played,
                record.wins,
                record.losses,
                record.win_percentage,
                record.loss_percentage,
                record.runs_for,
                record.runs_against,
                record.position,
                record.stage,
                record.group_name,
                record.source_payload_ref,
                record.source_payload_checksum,
                record.schema_version,
                canonical,
            )
            if self._append(
                table="api_sports_standing_snapshots",
                id_column="snapshot_id",
                record_id=record.snapshot_id,
                columns=columns,
                values=values,
                canonical=canonical,
            ):
                inserted += 1
        return inserted

    def append_team_statistics(self, record: TeamStatisticsSnapshot) -> bool:
        canonical = canonical_json(record)
        columns = (
            "snapshot_id",
            "provider",
            "league_id",
            "season",
            "team_id",
            "team_name",
            "observed_at",
            "games_played_all",
            "games_played_home",
            "games_played_away",
            "wins_all",
            "wins_home",
            "wins_away",
            "win_pct_all",
            "win_pct_home",
            "win_pct_away",
            "losses_all",
            "losses_home",
            "losses_away",
            "loss_pct_all",
            "loss_pct_home",
            "loss_pct_away",
            "runs_for_total_all",
            "runs_for_total_home",
            "runs_for_total_away",
            "runs_for_avg_all",
            "runs_for_avg_home",
            "runs_for_avg_away",
            "runs_against_total_all",
            "runs_against_total_home",
            "runs_against_total_away",
            "runs_against_avg_all",
            "runs_against_avg_home",
            "runs_against_avg_away",
            "source_payload_ref",
            "source_payload_checksum",
            "schema_version",
            "canonical_record",
        )
        values = (
            record.snapshot_id,
            record.provider,
            record.league_id,
            record.season,
            record.team_id,
            record.team_name,
            record.observed_at,
            record.games_played_all,
            record.games_played_home,
            record.games_played_away,
            record.wins_all,
            record.wins_home,
            record.wins_away,
            record.win_pct_all,
            record.win_pct_home,
            record.win_pct_away,
            record.losses_all,
            record.losses_home,
            record.losses_away,
            record.loss_pct_all,
            record.loss_pct_home,
            record.loss_pct_away,
            record.runs_for_total_all,
            record.runs_for_total_home,
            record.runs_for_total_away,
            record.runs_for_avg_all,
            record.runs_for_avg_home,
            record.runs_for_avg_away,
            record.runs_against_total_all,
            record.runs_against_total_home,
            record.runs_against_total_away,
            record.runs_against_avg_all,
            record.runs_against_avg_home,
            record.runs_against_avg_away,
            record.source_payload_ref,
            record.source_payload_checksum,
            record.schema_version,
            canonical,
        )
        return self._append(
            table="api_sports_team_statistics_snapshots",
            id_column="snapshot_id",
            record_id=record.snapshot_id,
            columns=columns,
            values=values,
            canonical=canonical,
        )

    def append_catalog(self, record: ReferenceCatalogSnapshot) -> bool:
        canonical = canonical_json(record)
        columns = (
            "snapshot_id",
            "provider",
            "catalog_type",
            "observed_at",
            "source_payload_ref",
            "source_payload_checksum",
            "schema_version",
            "canonical_record",
        )
        values = (
            record.snapshot_id,
            record.provider,
            record.catalog_type,
            record.observed_at,
            record.source_payload_ref,
            record.source_payload_checksum,
            record.schema_version,
            canonical,
        )
        return self._append(
            table="api_sports_reference_catalog_snapshots",
            id_column="snapshot_id",
            record_id=record.snapshot_id,
            columns=columns,
            values=values,
            canonical=canonical,
        )

    def latest_standings_observed_at(
        self,
        *,
        league_id: int,
        season: int,
    ) -> datetime | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT MAX(observed_at) FROM api_sports_standing_snapshots "
                "WHERE league_id = %s AND season = %s",
                (league_id, season),
            )
            row = cursor.fetchone()
        return row[0] if row and row[0] is not None else None

    def latest_standing_team_ids(
        self,
        *,
        league_id: int,
        season: int,
    ) -> tuple[int, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT DISTINCT team_id FROM api_sports_standing_snapshots "
                "WHERE league_id = %s AND season = %s ORDER BY team_id",
                (league_id, season),
            )
            rows = cursor.fetchall()
        return tuple(int(row[0]) for row in rows)

    def latest_team_statistics_times(
        self,
        *,
        league_id: int,
        season: int,
    ) -> dict[int, datetime]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT team_id, MAX(observed_at) "
                "FROM api_sports_team_statistics_snapshots "
                "WHERE league_id = %s AND season = %s GROUP BY team_id",
                (league_id, season),
            )
            rows = cursor.fetchall()
        return {int(team_id): observed_at for team_id, observed_at in rows}

    def latest_catalog_observed_at(self, catalog_type: str) -> datetime | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT MAX(observed_at) FROM api_sports_reference_catalog_snapshots "
                "WHERE catalog_type = %s",
                (catalog_type,),
            )
            row = cursor.fetchone()
        return row[0] if row and row[0] is not None else None

    def counts(self) -> dict[str, int]:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM api_sports_standing_snapshots")
            standings = int(cursor.fetchone()[0])
            cursor.execute("SELECT COUNT(*) FROM api_sports_team_statistics_snapshots")
            team_stats = int(cursor.fetchone()[0])
            cursor.execute(
                "SELECT COUNT(*) FROM api_sports_reference_catalog_snapshots"
            )
            catalogs = int(cursor.fetchone()[0])
        return {
            "standing_snapshots": standings,
            "team_statistics_snapshots": team_stats,
            "reference_catalog_snapshots": catalogs,
        }
