"""PostgreSQL persistence and read models for Baseball operational acceptance."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .operational_acceptance import (
    ActivationGateAssessment,
    CanaryRunFact,
    canonical_operational_json,
)
from .postgres_repository import EvidenceConflictError


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


def _object(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise TypeError("canonical_record must decode to an object")
    return value


def _canary_from_object(value: Any) -> CanaryRunFact:
    payload = _object(value)
    payload["reason_codes"] = tuple(payload.get("reason_codes") or ())
    return CanaryRunFact(**payload)


class PostgreSQLOperationalAcceptanceRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def _append_fact(
        self,
        *,
        table: str,
        identity_column: str,
        identity: str,
        columns: tuple[str, ...],
        values: tuple[Any, ...],
    ) -> bool:
        placeholders = ["%s"] * len(values)
        placeholders[-1] = "%s::jsonb"
        insert = (
            f"INSERT INTO {table} ({', '.join(columns)}) "
            f"VALUES ({', '.join(placeholders)}) ON CONFLICT DO NOTHING"
        )
        with self.connection.cursor() as cursor:
            cursor.execute(insert, values)
            if cursor.rowcount == 1:
                self.connection.commit()
                return True
            cursor.execute(
                f"SELECT canonical_record FROM {table} WHERE {identity_column} = %s",
                (identity,),
            )
            row = cursor.fetchone()
        if row is None or _canonical_text(row[0]) != values[-1]:
            self.connection.rollback()
            raise EvidenceConflictError(f"conflicting immutable identity: {identity}")
        self.connection.commit()
        return False

    def append_canary(self, record: CanaryRunFact) -> bool:
        return self._append_fact(
            table="operational_canary_runs",
            identity_column="canary_id",
            identity=record.canary_id,
            columns=(
                "canary_id",
                "cycle_id",
                "started_at",
                "finished_at",
                "status",
                "max_api_requests",
                "api_requests",
                "fixture_observations_inserted",
                "observations_inserted",
                "errors",
                "archive_verified",
                "db_write_verified",
                "reason_codes",
                "schema_version",
                "canonical_record",
            ),
            values=(
                record.canary_id,
                record.cycle_id,
                record.started_at,
                record.finished_at,
                record.status,
                record.max_api_requests,
                record.api_requests,
                record.fixture_observations_inserted,
                record.observations_inserted,
                record.errors,
                record.archive_verified,
                record.db_write_verified,
                list(record.reason_codes),
                record.schema_version,
                canonical_operational_json(record),
            ),
        )

    def append_assessment(self, record: ActivationGateAssessment) -> bool:
        return self._append_fact(
            table="activation_gate_assessments",
            identity_column="assessment_id",
            identity=record.assessment_id,
            columns=(
                "assessment_id",
                "target",
                "assessed_at",
                "verdict",
                "reason_codes",
                "daily_request_budget",
                "cycle_request_cap",
                "cron_interval_minutes",
                "cycles_per_day",
                "worst_case_daily_requests",
                "request_headroom",
                "daily_reserve_required",
                "paper_mode",
                "collection_enabled",
                "api_key_configured",
                "raw_archive_configured",
                "migrations_current",
                "runtime_fresh",
                "canary_passed",
                "latest_canary_id",
                "schema_version",
                "canonical_record",
            ),
            values=(
                record.assessment_id,
                record.target,
                record.assessed_at,
                record.verdict,
                list(record.reason_codes),
                record.daily_request_budget,
                record.cycle_request_cap,
                record.cron_interval_minutes,
                record.cycles_per_day,
                record.worst_case_daily_requests,
                record.request_headroom,
                record.daily_reserve_required,
                record.paper_mode,
                record.collection_enabled,
                record.api_key_configured,
                record.raw_archive_configured,
                record.migrations_current,
                record.runtime_fresh,
                record.canary_passed,
                record.latest_canary_id,
                record.schema_version,
                canonical_operational_json(record),
            ),
        )

    def migrations_current(self, root: Path) -> bool:
        required = {path.name for path in (root / "migrations").glob("*.sql")}
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT version FROM schema_migrations")
            applied = {str(row[0]) for row in cursor.fetchall()}
        return required.issubset(applied)

    def runtime_fresh(
        self,
        *,
        as_of: datetime,
        max_age: timedelta,
    ) -> bool:
        current = as_of.astimezone(UTC)
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT MAX(finished_at) FROM runtime_cycles")
            row = cursor.fetchone()
        latest = None if row is None else row[0]
        if latest is None:
            return False
        return current - latest.astimezone(UTC) <= max_age

    def latest_canary(self) -> CanaryRunFact | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record FROM operational_canary_runs "
                "ORDER BY finished_at DESC, canary_id DESC LIMIT 1"
            )
            row = cursor.fetchone()
        return None if row is None else _canary_from_object(row[0])

    def canary_passed_recently(
        self,
        *,
        as_of: datetime,
        max_age: timedelta,
    ) -> tuple[bool, CanaryRunFact | None]:
        record = self.latest_canary()
        if record is None or record.status != "PASSED":
            return False, record
        finished = datetime.fromisoformat(record.finished_at).astimezone(UTC)
        return as_of.astimezone(UTC) - finished <= max_age, record

    def verify_canary_cycle(self, cycle_id: str) -> dict[str, Any]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT execution_mode, started_at, finished_at, "
                "fixture_observations_inserted, observations_inserted, errors "
                "FROM collection_cycles WHERE cycle_id = %s",
                (cycle_id,),
            )
            cycle = cursor.fetchone()
            if cycle is None:
                raise LookupError(cycle_id)
            cursor.execute(
                "SELECT EXISTS ("
                "SELECT 1 FROM fixture_observations "
                "WHERE inserted_at BETWEEN %s AND %s "
                "AND source_payload_ref LIKE 's3://%%'"
                ")",
                (cycle[1], cycle[2]),
            )
            fixture_archive = bool(cursor.fetchone()[0])
            cursor.execute(
                "SELECT EXISTS ("
                "SELECT 1 FROM odds_observations "
                "WHERE inserted_at BETWEEN %s AND %s "
                "AND source_payload_ref LIKE 's3://%%'"
                ")",
                (cycle[1], cycle[2]),
            )
            odds_archive = bool(cursor.fetchone()[0])

        fixture_writes = int(cycle[3])
        odds_writes = int(cycle[4])
        return {
            "execution_mode": str(cycle[0]),
            "fixture_observations_inserted": fixture_writes,
            "observations_inserted": odds_writes,
            "errors": int(cycle[5]),
            "archive_verified": fixture_archive and odds_archive,
            "db_write_verified": fixture_writes > 0 and odds_writes > 0,
        }

    def performance_snapshot(self) -> dict[str, Any]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT settled_picks, wins, losses, pushes, "
                "graded_probability_picks, realized_profit_per_unit, "
                "roi_per_unit_staked, brier_score, log_loss, clv_available, "
                "clv_unavailable, clv_coverage, average_clv_probability_delta, "
                "average_clv_price_ratio, positive_clv_rate "
                "FROM baseball_moneyline_performance"
            )
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("performance projection returned no row")
        names = (
            "settled_picks",
            "wins",
            "losses",
            "pushes",
            "graded_probability_picks",
            "realized_profit_per_unit",
            "roi_per_unit_staked",
            "brier_score",
            "log_loss",
            "clv_available",
            "clv_unavailable",
            "clv_coverage",
            "average_clv_probability_delta",
            "average_clv_price_ratio",
            "positive_clv_rate",
        )
        return {
            name: (
                None
                if value is None
                else int(value)
                if name
                in {
                    "settled_picks",
                    "wins",
                    "losses",
                    "pushes",
                    "graded_probability_picks",
                    "clv_available",
                    "clv_unavailable",
                }
                else float(value)
            )
            for name, value in zip(names, row, strict=True)
        }

    def performance_breakdown(self) -> tuple[dict[str, Any], ...]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT dimension, dimension_value, settled_picks, "
                "realized_profit_per_unit, roi_per_unit_staked, brier_score, "
                "log_loss, average_clv_probability_delta "
                "FROM baseball_moneyline_performance_breakdown "
                "ORDER BY dimension, dimension_value"
            )
            rows = cursor.fetchall()
        return tuple(
            {
                "dimension": str(row[0]),
                "dimension_value": str(row[1]),
                "settled_picks": int(row[2]),
                "realized_profit_per_unit": float(row[3]),
                "roi_per_unit_staked": None if row[4] is None else float(row[4]),
                "brier_score": None if row[5] is None else float(row[5]),
                "log_loss": None if row[6] is None else float(row[6]),
                "average_clv_probability_delta": (
                    None if row[7] is None else float(row[7])
                ),
            }
            for row in rows
        )
