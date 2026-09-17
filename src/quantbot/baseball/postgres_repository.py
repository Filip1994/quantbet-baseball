"""PostgreSQL adapter for the canonical baseball evidence repository."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
import json
from typing import Any, Protocol

from .evidence import OddsObservation, PickEvent, canonical_json
from .evidence_repository import RepositoryStats


class CursorLike(Protocol):
    rowcount: int

    def execute(self, operation: str, parameters: Any = ...) -> Any: ...

    def fetchone(self) -> Any: ...

    def fetchall(self) -> list[Any]: ...

    def __enter__(self) -> "CursorLike": ...

    def __exit__(self, *args: Any) -> None: ...


class ConnectionLike(Protocol):
    def cursor(self) -> CursorLike: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class EvidenceConflictError(ValueError):
    """Raised when an immutable identity is reused with different content."""


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


def _canonical_object(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise TypeError("canonical_record must decode to a JSON object")
    return value


class PostgreSQLEvidenceRepository:
    """DB-API PostgreSQL implementation of the evidence repository contract."""

    def __init__(self, connection: ConnectionLike) -> None:
        self._connection = connection

    @staticmethod
    def _observation_values(record: OddsObservation) -> tuple[Any, ...]:
        return (
            record.observation_id,
            record.game_id,
            record.market_family,
            record.line,
            record.selection,
            record.bookmaker,
            record.decimal_odds,
            record.raw_price,
            record.observed_at,
            record.retrieved_at,
            record.kickoff_at,
            record.source_payload_ref,
            record.source_payload_checksum,
            record.schema_version,
            record.market_status,
            canonical_json(record),
        )

    @staticmethod
    def _pick_values(record: PickEvent) -> tuple[Any, ...]:
        return (
            record.pick_id,
            record.game_id,
            record.market_family,
            record.line,
            record.selection,
            record.decision,
            record.decision_reason,
            record.decision_at,
            record.model_version,
            record.feature_snapshot_ref,
            record.market_snapshot_ref,
            record.decision_decimal_odds,
            record.model_probability,
            record.fair_decimal_odds,
            record.market_implied_probability,
            record.edge,
            record.expected_value_per_unit,
            record.uncertainty_metric,
            record.source_data_cutoff_at,
            record.schema_version,
            canonical_json(record),
        )

    def _append(
        self,
        table: str,
        identity: str,
        values: tuple[Any, ...],
        columns: tuple[str, ...],
        *,
        commit: bool = True,
    ) -> bool:
        identity_column = (
            "observation_id" if table == "odds_observations" else "pick_id"
        )
        placeholders = ["%s"] * len(values)
        placeholders[-1] = "%s::jsonb"
        insert = (
            f"INSERT INTO {table} ({', '.join(columns)}) "
            f"VALUES ({', '.join(placeholders)}) ON CONFLICT DO NOTHING"
        )
        compare = (
            f"SELECT canonical_record FROM {table} "
            f"WHERE {identity_column} = %s"
        )

        with self._connection.cursor() as cursor:
            cursor.execute(insert, values)
            if cursor.rowcount == 1:
                if commit:
                    self._connection.commit()
                return True

            cursor.execute(compare, (identity,))
            existing = cursor.fetchone()
            if existing is None or _canonical_text(existing[0]) != values[-1]:
                self._connection.rollback()
                raise EvidenceConflictError(
                    f"conflicting immutable identity: {identity}"
                )

        if commit:
            self._connection.commit()
        return False

    def append_observation(self, record: OddsObservation) -> bool:
        columns = (
            "observation_id",
            "game_id",
            "market_family",
            "line",
            "selection",
            "bookmaker",
            "decimal_odds",
            "raw_price",
            "observed_at",
            "retrieved_at",
            "kickoff_at",
            "source_payload_ref",
            "source_payload_checksum",
            "schema_version",
            "market_status",
            "canonical_record",
        )
        return self._append(
            "odds_observations",
            record.observation_id,
            self._observation_values(record),
            columns,
        )

    def append_pick_event(self, record: PickEvent) -> bool:
        columns = (
            "pick_id",
            "game_id",
            "market_family",
            "line",
            "selection",
            "decision",
            "decision_reason",
            "decision_at",
            "model_version",
            "feature_snapshot_ref",
            "market_snapshot_ref",
            "decision_decimal_odds",
            "model_probability",
            "fair_decimal_odds",
            "market_implied_probability",
            "edge",
            "expected_value_per_unit",
            "uncertainty_metric",
            "source_data_cutoff_at",
            "schema_version",
            "canonical_record",
        )
        return self._append(
            "pick_events",
            record.pick_id,
            self._pick_values(record),
            columns,
        )

    def append_observations(self, records: Iterable[OddsObservation]) -> int:
        batch = tuple(records)
        if not batch:
            return 0

        columns = (
            "observation_id",
            "game_id",
            "market_family",
            "line",
            "selection",
            "bookmaker",
            "decimal_odds",
            "raw_price",
            "observed_at",
            "retrieved_at",
            "kickoff_at",
            "source_payload_ref",
            "source_payload_checksum",
            "schema_version",
            "market_status",
            "canonical_record",
        )

        inserted = 0
        try:
            for record in batch:
                if self._append(
                    "odds_observations",
                    record.observation_id,
                    self._observation_values(record),
                    columns,
                    commit=False,
                ):
                    inserted += 1
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return inserted

    def get_observation(self, observation_id: str) -> OddsObservation | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record FROM odds_observations "
                "WHERE observation_id = %s",
                (observation_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return OddsObservation(**_canonical_object(row[0]))

    def get_pick_event(self, pick_id: str) -> PickEvent | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record FROM pick_events WHERE pick_id = %s",
                (pick_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return PickEvent(**_canonical_object(row[0]))

    def observations(self) -> tuple[OddsObservation, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record FROM odds_observations "
                "ORDER BY observed_at, observation_id"
            )
            rows = cursor.fetchall()
        return tuple(
            OddsObservation(**_canonical_object(row[0])) for row in rows
        )

    def pick_events(self) -> tuple[PickEvent, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record FROM pick_events "
                "ORDER BY decision_at, pick_id"
            )
            rows = cursor.fetchall()
        return tuple(PickEvent(**_canonical_object(row[0])) for row in rows)

    def latest_observation_times(self) -> dict[str, datetime]:
        """Return the latest captured pregame observation for every game."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT game_id, MAX(observed_at) "
                "FROM odds_observations GROUP BY game_id"
            )
            rows = cursor.fetchall()
        return {str(game_id): observed_at for game_id, observed_at in rows}

    def stats(self) -> RepositoryStats:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM odds_observations")
            observations = int(cursor.fetchone()[0])
            cursor.execute("SELECT COUNT(*) FROM pick_events")
            pick_events = int(cursor.fetchone()[0])
        return RepositoryStats(
            observations=observations,
            pick_events=pick_events,
        )
