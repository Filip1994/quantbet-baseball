"""PostgreSQL storage/query boundary for API-Sports game-history evidence."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from .game_history import GameHistorySnapshot, canonical_game_history_json
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


class PostgreSQLGameHistoryRepository:
    def __init__(self, connection: ConnectionLike) -> None:
        self._connection = connection

    def append_snapshots(self, records: Iterable[GameHistorySnapshot]) -> int:
        inserted = 0
        for record in records:
            if self.append_snapshot(record):
                inserted += 1
        return inserted

    def append_snapshot(self, record: GameHistorySnapshot) -> bool:
        canonical = canonical_game_history_json(record)
        columns = (
            "snapshot_id",
            "provider",
            "provider_game_id",
            "observed_at",
            "scheduled_first_pitch",
            "provider_timezone",
            "status_long",
            "status_short",
            "league_id",
            "season",
            "home_team_id",
            "home_team_name",
            "away_team_id",
            "away_team_name",
            "home_score",
            "away_score",
            "home_hits",
            "away_hits",
            "home_errors",
            "away_errors",
            "home_innings",
            "away_innings",
            "source_payload_ref",
            "source_payload_checksum",
            "schema_version",
            "canonical_record",
        )
        values = (
            record.snapshot_id,
            record.provider,
            record.provider_game_id,
            record.observed_at,
            record.scheduled_first_pitch,
            record.provider_timezone,
            record.status_long,
            record.status_short,
            record.league_id,
            record.season,
            record.home_team_id,
            record.home_team_name,
            record.away_team_id,
            record.away_team_name,
            record.home_score,
            record.away_score,
            record.home_hits,
            record.away_hits,
            record.home_errors,
            record.away_errors,
            json.dumps(record.home_innings, sort_keys=True, separators=(",", ":")),
            json.dumps(record.away_innings, sort_keys=True, separators=(",", ":")),
            record.source_payload_ref,
            record.source_payload_checksum,
            record.schema_version,
            canonical,
        )
        placeholders = ["%s"] * len(values)
        placeholders[20] = "%s::jsonb"
        placeholders[21] = "%s::jsonb"
        placeholders[-1] = "%s::jsonb"
        query = (
            "INSERT INTO api_sports_game_history_snapshots "
            f"({', '.join(columns)}) VALUES ({', '.join(placeholders)}) "
            "ON CONFLICT DO NOTHING"
        )
        with self._connection.cursor() as cursor:
            cursor.execute(query, values)
            if cursor.rowcount == 1:
                self._connection.commit()
                return True
            cursor.execute(
                "SELECT canonical_record FROM api_sports_game_history_snapshots "
                "WHERE snapshot_id = %s",
                (record.snapshot_id,),
            )
            row = cursor.fetchone()
        if row is None or _canonical_text(row[0]) != canonical:
            self._connection.rollback()
            raise EvidenceConflictError(
                f"conflicting game-history snapshot identity: {record.snapshot_id}"
            )
        self._connection.commit()
        return False

    def latest_observed_at(
        self,
        *,
        league_id: int,
        season: int,
    ) -> datetime | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT MAX(observed_at) FROM api_sports_game_history_snapshots "
                "WHERE league_id = %s AND season = %s",
                (league_id, season),
            )
            row = cursor.fetchone()
        return row[0] if row and row[0] is not None else None

    def latest_snapshots_for_team_before(
        self,
        *,
        team_id: int,
        league_id: int,
        season: int,
        scheduled_before: datetime,
        observed_by: datetime,
    ) -> tuple[GameHistorySnapshot, ...]:
        """Return latest point-in-time snapshot per provider game for one team."""

        query = """
            SELECT DISTINCT ON (provider_game_id)
                canonical_record
            FROM api_sports_game_history_snapshots
            WHERE league_id = %s
              AND season = %s
              AND (home_team_id = %s OR away_team_id = %s)
              AND scheduled_first_pitch < %s
              AND observed_at <= %s
            ORDER BY provider_game_id, observed_at DESC, snapshot_id DESC
        """
        with self._connection.cursor() as cursor:
            cursor.execute(
                query,
                (
                    league_id,
                    season,
                    team_id,
                    team_id,
                    scheduled_before,
                    observed_by,
                ),
            )
            rows = cursor.fetchall()

        records: list[GameHistorySnapshot] = []
        for row in rows:
            value = row[0]
            if isinstance(value, str):
                value = json.loads(value)
            if not isinstance(value, dict):
                continue
            records.append(GameHistorySnapshot(**value))
        return tuple(
            sorted(
                records,
                key=lambda item: (
                    item.scheduled_first_pitch,
                    item.provider_game_id,
                ),
            )
        )

    def counts(self) -> dict[str, int]:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM api_sports_game_history_snapshots")
            total = int(cursor.fetchone()[0])
            cursor.execute(
                "SELECT COUNT(DISTINCT provider_game_id) "
                "FROM api_sports_game_history_snapshots"
            )
            games = int(cursor.fetchone()[0])
        return {"snapshots": total, "distinct_games": games}
