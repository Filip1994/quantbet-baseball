"""PostgreSQL adapter for the canonical baseball evidence repository."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Protocol, Self

from .evidence import OddsObservation, PickEvent, canonical_json
from .evidence_repository import RepositoryStats
from .fixture_evidence import FixtureObservation, canonical_fixture_json
from .odds_poll_evidence import OddsPollAttempt, canonical_odds_poll_attempt_json
from .runtime_evidence import CollectionCycle, canonical_collection_cycle_json


class CursorLike(Protocol):
    rowcount: int

    def execute(self, operation: str, parameters: Any = ...) -> Any: ...

    def fetchone(self) -> Any: ...

    def fetchall(self) -> list[Any]: ...

    def __enter__(self) -> Self: ...

    def __exit__(self, *args: object) -> None: ...


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


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


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
        identity_columns = {
            "odds_observations": "observation_id",
            "odds_poll_attempts": "poll_attempt_id",
            "pick_events": "pick_id",
            "fixture_observations": "fixture_observation_id",
            "collection_cycles": "cycle_id",
        }
        identity_column = identity_columns[table]
        placeholders = ["%s"] * len(values)
        placeholders[-1] = "%s::jsonb"
        insert = (
            f"INSERT INTO {table} ({', '.join(columns)}) "
            f"VALUES ({', '.join(placeholders)}) ON CONFLICT DO NOTHING"
        )
        compare = f"SELECT canonical_record FROM {table} WHERE {identity_column} = %s"

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

    @staticmethod
    def _poll_attempt_values(record: OddsPollAttempt) -> tuple[Any, ...]:
        return (
            record.poll_attempt_id,
            record.game_id,
            record.provider,
            record.provider_game_id,
            record.attempted_at,
            record.kickoff_at,
            record.response_rows,
            record.raw_market_rows,
            record.canonical_rows,
            record.source_payload_ref,
            record.source_payload_checksum,
            record.schema_version,
            canonical_odds_poll_attempt_json(record),
        )

    def append_odds_poll_attempt(self, record: OddsPollAttempt) -> bool:
        columns = (
            "poll_attempt_id",
            "game_id",
            "provider",
            "provider_game_id",
            "attempted_at",
            "kickoff_at",
            "response_rows",
            "raw_market_rows",
            "canonical_rows",
            "source_payload_ref",
            "source_payload_checksum",
            "schema_version",
            "canonical_record",
        )
        return self._append(
            "odds_poll_attempts",
            record.poll_attempt_id,
            self._poll_attempt_values(record),
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

    def append_fixture_observations(
        self,
        records: Iterable[FixtureObservation],
    ) -> int:
        batch = tuple(records)
        if not batch:
            return 0

        columns = (
            "fixture_observation_id",
            "game_id",
            "provider",
            "provider_game_id",
            "league",
            "home_team_id",
            "home_team_name",
            "away_team_id",
            "away_team_name",
            "kickoff_at",
            "provider_status",
            "observed_at",
            "source_payload_ref",
            "source_payload_checksum",
            "schema_version",
            "canonical_record",
        )

        inserted = 0
        try:
            for record in batch:
                with self._connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO fixtures (game_id, provider, provider_game_id, "
                        "home_team_id, away_team_id) VALUES (%s, %s, %s, %s, %s) "
                        "ON CONFLICT DO NOTHING",
                        (
                            record.game_id,
                            record.provider,
                            record.provider_game_id,
                            record.home_team_id,
                            record.away_team_id,
                        ),
                    )
                    cursor.execute(
                        "SELECT provider, provider_game_id, home_team_id, away_team_id "
                        "FROM fixtures WHERE game_id = %s",
                        (record.game_id,),
                    )
                    fixture = cursor.fetchone()
                expected = (
                    record.provider,
                    record.provider_game_id,
                    record.home_team_id,
                    record.away_team_id,
                )
                if fixture is None or tuple(fixture) != expected:
                    raise EvidenceConflictError(
                        f"conflicting fixture identity: {record.game_id}"
                    )

                values = (
                    record.fixture_observation_id,
                    record.game_id,
                    record.provider,
                    record.provider_game_id,
                    record.league,
                    record.home_team_id,
                    record.home_team_name,
                    record.away_team_id,
                    record.away_team_name,
                    record.kickoff_at,
                    record.provider_status,
                    record.observed_at,
                    record.source_payload_ref,
                    record.source_payload_checksum,
                    record.schema_version,
                    canonical_fixture_json(record),
                )
                if self._append(
                    "fixture_observations",
                    record.fixture_observation_id,
                    values,
                    columns,
                    commit=False,
                ):
                    inserted += 1
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return inserted

    def append_collection_cycle(self, record: CollectionCycle) -> bool:
        columns = (
            "cycle_id",
            "started_at",
            "finished_at",
            "status",
            "execution_mode",
            "games_seen",
            "fixture_observations_inserted",
            "pregame_games",
            "due_events",
            "games_selected",
            "odds_calls",
            "raw_market_rows",
            "canonical_rows",
            "observations_inserted",
            "api_requests",
            "api_remaining",
            "errors",
            "schema_version",
            "canonical_record",
        )
        values = (
            record.cycle_id,
            record.started_at,
            record.finished_at,
            record.status,
            record.execution_mode,
            record.games_seen,
            record.fixture_observations_inserted,
            record.pregame_games,
            record.due_events,
            record.games_selected,
            record.odds_calls,
            record.raw_market_rows,
            record.canonical_rows,
            record.observations_inserted,
            record.api_requests,
            record.api_remaining,
            record.errors,
            record.schema_version,
            canonical_collection_cycle_json(record),
        )
        return self._append(
            "collection_cycles",
            record.cycle_id,
            values,
            columns,
        )

    def append_runtime_cycle(
        self,
        *,
        run_id: str,
        started_at: datetime,
        finished_at: datetime,
        collection_enabled: bool,
        mode: str,
        status: str,
        stats: dict[str, Any],
    ) -> None:
        payload = json.dumps(
            stats,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO runtime_cycles (run_id, started_at, finished_at, "
                "collection_enabled, mode, status, stats) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)",
                (
                    run_id,
                    started_at,
                    finished_at,
                    collection_enabled,
                    mode,
                    status,
                    payload,
                ),
            )
        self._connection.commit()

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
        return tuple(OddsObservation(**_canonical_object(row[0])) for row in rows)

    def pick_events(self) -> tuple[PickEvent, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record FROM pick_events ORDER BY decision_at, pick_id"
            )
            rows = cursor.fetchall()
        return tuple(PickEvent(**_canonical_object(row[0])) for row in rows)

    def latest_odds_poll_times(self) -> dict[str, datetime]:
        """Return the latest successful provider odds poll for every game."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT game_id, MAX(attempted_at) "
                "FROM odds_poll_attempts GROUP BY game_id"
            )
            rows = cursor.fetchall()
        return {str(game_id): attempted_at for game_id, attempted_at in rows}

    def latest_observation_times(self) -> dict[str, datetime]:
        """Return the latest captured pregame observation for every game."""

        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT game_id, MAX(observed_at) "
                "FROM odds_observations GROUP BY game_id"
            )
            rows = cursor.fetchall()
        return {str(game_id): observed_at for game_id, observed_at in rows}

    def health_snapshot(self) -> dict[str, Any]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*), COUNT(DISTINCT game_id), MAX(observed_at) "
                "FROM fixture_observations"
            )
            fixture_count, fixture_games, latest_fixture = cursor.fetchone()

            cursor.execute(
                "SELECT COUNT(*), COUNT(DISTINCT game_id), "
                "COUNT(DISTINCT bookmaker), MAX(observed_at) "
                "FROM odds_observations"
            )
            odds_count, odds_games, bookmakers, latest_odds = cursor.fetchone()

            cursor.execute(
                "SELECT COUNT(*), COUNT(DISTINCT game_id), MAX(attempted_at) "
                "FROM odds_poll_attempts"
            )
            poll_count, polled_games, latest_poll = cursor.fetchone()

            cursor.execute("SELECT COUNT(*) FROM pick_events")
            pick_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM model_predictions")
            prediction_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM value_evaluations")
            evaluation_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM final_quote_verifications")
            verification_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM registered_picks")
            registered_pick_count = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM pick_monitoring_states WHERE state = 'MONITORING'"
            )
            monitored_pick_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM pick_closing_finalizations")
            closing_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM game_result_facts")
            result_fact_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM pick_settlements")
            settlement_count = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM pick_settlements WHERE clv_status = 'AVAILABLE'"
            )
            clv_available_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*), MAX(finished_at) FROM collection_cycles")
            collection_count, latest_collection = cursor.fetchone()

            cursor.execute("SELECT COUNT(*), MAX(finished_at) FROM runtime_cycles")
            runtime_count, latest_runtime = cursor.fetchone()

        return {
            "fixture_observations": int(fixture_count),
            "distinct_fixtures": int(fixture_games),
            "odds_observations": int(odds_count),
            "distinct_quote_games": int(odds_games),
            "bookmakers": int(bookmakers),
            "odds_poll_attempts": int(poll_count),
            "distinct_polled_games": int(polled_games),
            "latest_odds_poll_attempt_at": _iso_or_none(latest_poll),
            "pick_events": int(pick_count),
            "model_predictions": int(prediction_count),
            "value_evaluations": int(evaluation_count),
            "final_quote_verifications": int(verification_count),
            "registered_picks": int(registered_pick_count),
            "monitored_picks": int(monitored_pick_count),
            "closing_finalizations": int(closing_count),
            "game_result_facts": int(result_fact_count),
            "settled_picks": int(settlement_count),
            "clv_available": int(clv_available_count),
            "collection_cycles": int(collection_count),
            "runtime_cycles": int(runtime_count),
            "latest_fixture_observed_at": _iso_or_none(latest_fixture),
            "latest_odds_observed_at": _iso_or_none(latest_odds),
            "latest_collection_finished_at": _iso_or_none(latest_collection),
            "latest_runtime_finished_at": _iso_or_none(latest_runtime),
        }

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
