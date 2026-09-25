"""PostgreSQL-backed operational dashboard, bulletin and acceptance gate."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from .budget_policy import BaseballAPIBudgetPolicy
from .operational_product import (
    AcceptanceCriterion,
    CollectionCanaryRun,
    OperationalAcceptanceRun,
    build_acceptance_run,
    canonical_acceptance_json,
    canonical_canary_json,
)
from .postgres_repository import EvidenceConflictError


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _object(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise TypeError("canonical_record must decode to an object")
    return value


def _canary_from_object(value: Any) -> CollectionCanaryRun:
    payload = _object(value)
    payload["reason_codes"] = tuple(payload.get("reason_codes") or ())
    return CollectionCanaryRun(**payload)


class PostgreSQLOperationalRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def append_canary(self, record: CollectionCanaryRun) -> bool:
        canonical = canonical_canary_json(record)
        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO collection_canary_runs "
                "(canary_id, started_at, finished_at, max_api_requests, "
                "max_odds_requests, status, api_requests, "
                "fixture_observations_inserted, observations_inserted, errors, "
                "passed, reason_codes, schema_version, canonical_record) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s::jsonb) ON CONFLICT DO NOTHING",
                (
                    record.canary_id,
                    record.started_at,
                    record.finished_at,
                    record.max_api_requests,
                    record.max_odds_requests,
                    record.status,
                    record.api_requests,
                    record.fixture_observations_inserted,
                    record.observations_inserted,
                    record.errors,
                    record.passed,
                    list(record.reason_codes),
                    record.schema_version,
                    canonical,
                ),
            )
            inserted = cursor.rowcount == 1
            cursor.execute(
                "SELECT canonical_record FROM collection_canary_runs "
                "WHERE canary_id = %s",
                (record.canary_id,),
            )
            row = cursor.fetchone()
        if row is None:
            self.connection.rollback()
            raise EvidenceConflictError("canary insert did not resolve")
        existing = _canary_from_object(row[0])
        if not inserted and canonical_canary_json(existing) != canonical:
            self.connection.rollback()
            raise EvidenceConflictError(
                f"conflicting canary identity: {record.canary_id}"
            )
        self.connection.commit()
        return inserted

    def latest_canary(self) -> CollectionCanaryRun | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record FROM collection_canary_runs "
                "ORDER BY finished_at DESC, canary_id DESC LIMIT 1"
            )
            row = cursor.fetchone()
        return None if row is None else _canary_from_object(row[0])

    def append_acceptance(self, record: OperationalAcceptanceRun) -> bool:
        canonical = canonical_acceptance_json(record)
        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO operational_acceptance_runs "
                "(acceptance_id, evaluated_at, policy_version, status, criteria, "
                "budget, integrity_anomalies, latest_canary_id, schema_version, "
                "canonical_record) "
                "VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, "
                "%s::jsonb) ON CONFLICT DO NOTHING",
                (
                    record.acceptance_id,
                    record.evaluated_at,
                    record.policy_version,
                    record.status,
                    json.dumps(record.criteria, sort_keys=True),
                    json.dumps(record.budget, sort_keys=True),
                    record.integrity_anomalies,
                    record.latest_canary_id,
                    record.schema_version,
                    canonical,
                ),
            )
            inserted = cursor.rowcount == 1
            cursor.execute(
                "SELECT canonical_record FROM operational_acceptance_runs "
                "WHERE acceptance_id = %s",
                (record.acceptance_id,),
            )
            row = cursor.fetchone()
        if row is None:
            self.connection.rollback()
            raise EvidenceConflictError("acceptance insert did not resolve")
        existing = OperationalAcceptanceRun(**_object(row[0]))
        if not inserted and canonical_acceptance_json(existing) != canonical:
            self.connection.rollback()
            raise EvidenceConflictError(
                f"conflicting acceptance identity: {record.acceptance_id}"
            )
        self.connection.commit()
        return inserted

    def integrity_anomalies(self) -> dict[str, int]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT entry_provenance_anomalies, closing_provenance_anomalies, "
                "settlement_provenance_anomalies FROM baseball_operational_integrity"
            )
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("operational integrity view returned no row")
        return {
            "entry_provenance_anomalies": int(row[0]),
            "closing_provenance_anomalies": int(row[1]),
            "settlement_provenance_anomalies": int(row[2]),
        }

    def evidence_health(self, *, as_of: datetime) -> dict[str, Any]:
        current = _utc(as_of, "as_of")
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*), MAX(finished_at) FROM runtime_cycles"
            )
            runtime_count, latest_runtime = cursor.fetchone()

            cursor.execute(
                "SELECT COUNT(*), MAX(observed_at) FROM fixture_observations"
            )
            fixture_count, latest_fixture = cursor.fetchone()

            cursor.execute(
                "SELECT COUNT(*), MAX(observed_at) FROM odds_observations "
                "WHERE market_family = 'moneyline'"
            )
            odds_count, latest_odds = cursor.fetchone()

            cursor.execute("SELECT COUNT(*) FROM registered_picks")
            registered_picks = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM pick_closing_finalizations")
            closing_finalizations = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM pick_settlements")
            settlements = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COALESCE(SUM(api_requests), 0) FROM collection_cycles "
                "WHERE finished_at >= %s",
                (current - timedelta(hours=24),),
            )
            requests_last_24h = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) AS total, "
                "COUNT(*) FILTER (WHERE source_payload_ref LIKE 's3://%%') AS remote "
                "FROM ("
                "SELECT source_payload_ref FROM fixture_observations "
                "UNION ALL "
                "SELECT source_payload_ref FROM odds_observations "
                "UNION ALL "
                "SELECT source_payload_ref FROM game_result_facts"
                ") evidence"
            )
            archive_total, archive_remote = cursor.fetchone()

        return {
            "runtime_cycles": int(runtime_count),
            "latest_runtime_at": (
                None if latest_runtime is None else latest_runtime.isoformat()
            ),
            "fixture_observations": int(fixture_count),
            "latest_fixture_at": (
                None if latest_fixture is None else latest_fixture.isoformat()
            ),
            "moneyline_observations": int(odds_count),
            "latest_moneyline_at": None if latest_odds is None else latest_odds.isoformat(),
            "registered_picks": int(registered_picks),
            "closing_finalizations": int(closing_finalizations),
            "settlements": int(settlements),
            "api_requests_last_24h": int(requests_last_24h),
            "archive_evidence_rows": int(archive_total),
            "remote_archive_rows": int(archive_remote),
        }

    def performance_snapshot(self) -> dict[str, Any]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT registered_picks, closing_finalizations, settled_picks, "
                "pending_settlement, wins, losses, pushes, realized_profit_per_unit, "
                "clv_available, clv_unavailable, average_clv_probability_delta, "
                "average_clv_price_ratio FROM baseball_moneyline_dashboard"
            )
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("moneyline dashboard returned no row")

        settled = int(row[2])
        decisions = int(row[4]) + int(row[5])
        clv_total = int(row[8]) + int(row[9])
        profit = float(row[7])
        return {
            "registered_picks": int(row[0]),
            "closing_finalizations": int(row[1]),
            "settled_picks": settled,
            "pending_settlement": int(row[3]),
            "wins": int(row[4]),
            "losses": int(row[5]),
            "pushes": int(row[6]),
            "realized_profit_per_unit": profit,
            "yield_per_pick": None if settled == 0 else profit / settled,
            "win_rate_ex_push": None if decisions == 0 else int(row[4]) / decisions,
            "clv_available": int(row[8]),
            "clv_unavailable": int(row[9]),
            "clv_coverage": None if clv_total == 0 else int(row[8]) / clv_total,
            "average_clv_probability_delta": (
                None if row[10] is None else float(row[10])
            ),
            "average_clv_price_ratio": None if row[11] is None else float(row[11]),
        }

    def daily_bulletin(
        self,
        *,
        as_of: datetime,
        horizon_hours: int = 36,
        recent_hours: int = 24,
        limit: int = 50,
    ) -> dict[str, Any]:
        current = _utc(as_of, "as_of")
        if horizon_hours < 1 or recent_hours < 1 or limit < 1:
            raise ValueError("bulletin windows and limit must be positive")

        columns = (
            "pick_id, game_id, league, away_team_name, home_team_name, selection, "
            "bookmaker, entry_odds, model_probability, entry_market_probability, "
            "edge, expected_value_per_unit, model_version, registered_at, kickoff_at, "
            "provider_status, fixture_observed_at, lifecycle_state, closing_outcome, "
            "closing_finalized_at, settlement_outcome, profit_per_unit, clv_status, "
            "closing_odds, clv_probability_delta, settled_at"
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {columns} FROM baseball_moneyline_daily_bulletin "
                "WHERE settlement_outcome IS NULL AND kickoff_at >= %s "
                "AND kickoff_at <= %s ORDER BY kickoff_at, pick_id LIMIT %s",
                (current, current + timedelta(hours=horizon_hours), limit),
            )
            upcoming = cursor.fetchall()
            cursor.execute(
                f"SELECT {columns} FROM baseball_moneyline_daily_bulletin "
                "WHERE settled_at >= %s AND settled_at <= %s "
                "ORDER BY settled_at DESC, pick_id LIMIT %s",
                (current - timedelta(hours=recent_hours), current, limit),
            )
            recent = cursor.fetchall()

        names = [
            "pick_id",
            "game_id",
            "league",
            "away_team_name",
            "home_team_name",
            "selection",
            "bookmaker",
            "entry_odds",
            "model_probability",
            "entry_market_probability",
            "edge",
            "expected_value_per_unit",
            "model_version",
            "registered_at",
            "kickoff_at",
            "provider_status",
            "fixture_observed_at",
            "lifecycle_state",
            "closing_outcome",
            "closing_finalized_at",
            "settlement_outcome",
            "profit_per_unit",
            "clv_status",
            "closing_odds",
            "clv_probability_delta",
            "settled_at",
        ]

        def encode(row: Any) -> dict[str, Any]:
            payload: dict[str, Any] = {}
            for name, value in zip(names, row, strict=True):
                if isinstance(value, datetime):
                    payload[name] = value.isoformat()
                elif hasattr(value, "as_tuple"):
                    payload[name] = float(value)
                else:
                    payload[name] = value
            return payload

        return {
            "as_of": current.isoformat(),
            "horizon_hours": horizon_hours,
            "recent_hours": recent_hours,
            "upcoming": [encode(row) for row in upcoming],
            "recent_settlements": [encode(row) for row in recent],
        }

    def acceptance_report(
        self,
        *,
        as_of: datetime,
        budget_policy: BaseballAPIBudgetPolicy,
        paper_mode: bool,
    ) -> OperationalAcceptanceRun:
        current = _utc(as_of, "as_of")
        health = self.evidence_health(as_of=current)
        anomalies = self.integrity_anomalies()
        anomaly_total = sum(anomalies.values())
        canary = self.latest_canary()

        archive_total = int(health["archive_evidence_rows"])
        archive_remote = int(health["remote_archive_rows"])
        downstream_ready = (
            int(health["registered_picks"]) >= int(health["settlements"])
            and int(health["closing_finalizations"]) >= int(health["settlements"])
        )
        criteria = (
            AcceptanceCriterion(
                code="PAPER_MODE",
                passed=paper_mode,
                detail="production runtime remains paper-only",
            ),
            AcceptanceCriterion(
                code="API_BUDGET_SAFE",
                passed=budget_policy.budget_safe,
                detail=(
                    f"{budget_policy.per_run_hard_limit} requests/run hard cap, "
                    f"{budget_policy.effective_headroom} requests/day headroom"
                ),
            ),
            AcceptanceCriterion(
                code="RUNTIME_TELEMETRY",
                passed=int(health["runtime_cycles"]) > 0,
                detail=f"runtime_cycles={health['runtime_cycles']}",
            ),
            AcceptanceCriterion(
                code="CANONICAL_FIXTURE_EVIDENCE",
                passed=int(health["fixture_observations"]) > 0,
                detail=f"fixture_observations={health['fixture_observations']}",
            ),
            AcceptanceCriterion(
                code="MONEYLINE_EVIDENCE",
                passed=int(health["moneyline_observations"]) > 0,
                detail=f"moneyline_observations={health['moneyline_observations']}",
            ),
            AcceptanceCriterion(
                code="REMOTE_ARCHIVE_PROVENANCE",
                passed=archive_total > 0 and archive_remote == archive_total,
                detail=f"remote_archive_rows={archive_remote}/{archive_total}",
            ),
            AcceptanceCriterion(
                code="IDENTITY_INTEGRITY",
                passed=anomaly_total == 0,
                detail=f"integrity_anomalies={anomaly_total}",
            ),
            AcceptanceCriterion(
                code="DOWNSTREAM_LIFECYCLE_READY",
                passed=downstream_ready,
                detail=(
                    f"registered={health['registered_picks']}, "
                    f"closed={health['closing_finalizations']}, "
                    f"settled={health['settlements']}"
                ),
            ),
            AcceptanceCriterion(
                code="BOUNDED_CANARY",
                passed=canary is not None and canary.passed,
                detail=(
                    "no canary recorded"
                    if canary is None
                    else f"canary={canary.canary_id}, passed={canary.passed}"
                ),
            ),
        )
        return build_acceptance_run(
            evaluated_at=current.isoformat(),
            budget_policy=budget_policy,
            criteria=criteria,
            integrity_anomalies=anomaly_total,
            latest_canary_id=None if canary is None else canary.canary_id,
        )

    def dashboard_snapshot(
        self,
        *,
        as_of: datetime,
        budget_policy: BaseballAPIBudgetPolicy,
        paper_mode: bool,
        collection_enabled: bool,
    ) -> dict[str, Any]:
        current = _utc(as_of, "as_of")
        health = self.evidence_health(as_of=current)
        performance = self.performance_snapshot()
        acceptance = self.acceptance_report(
            as_of=current,
            budget_policy=budget_policy,
            paper_mode=paper_mode,
        )
        alerts: list[dict[str, str]] = []

        latest_runtime_raw = health["latest_runtime_at"]
        if latest_runtime_raw is None:
            alerts.append(
                {
                    "severity": "CRITICAL",
                    "code": "NO_RUNTIME_TELEMETRY",
                    "message": "No Railway runtime cycle has been persisted.",
                }
            )
        else:
            latest_runtime = datetime.fromisoformat(str(latest_runtime_raw)).astimezone(UTC)
            age = (current - latest_runtime).total_seconds()
            if age > 30 * 60:
                alerts.append(
                    {
                        "severity": "CRITICAL",
                        "code": "STALE_RUNTIME",
                        "message": f"Latest runtime telemetry is {int(age)} seconds old.",
                    }
                )

        if int(health["api_requests_last_24h"]) > budget_policy.usable_daily_budget:
            alerts.append(
                {
                    "severity": "CRITICAL",
                    "code": "API_BUDGET_PRESSURE",
                    "message": "Last-24h API consumption exceeds usable daily budget.",
                }
            )

        if acceptance.integrity_anomalies:
            alerts.append(
                {
                    "severity": "CRITICAL",
                    "code": "PROVENANCE_ANOMALY",
                    "message": (
                        f"{acceptance.integrity_anomalies} operational provenance "
                        "anomalies detected."
                    ),
                }
            )

        if acceptance.status != "READY":
            alerts.append(
                {
                    "severity": "WARNING",
                    "code": "COLLECTION_ACTIVATION_BLOCKED",
                    "message": "Operational acceptance gate is not READY.",
                }
            )

        if not collection_enabled:
            alerts.append(
                {
                    "severity": "INFO",
                    "code": "COLLECTION_DISABLED",
                    "message": "Scheduled API collection is intentionally disabled.",
                }
            )

        return {
            "contract_version": "2.0",
            "generated_at": current.isoformat(),
            "system": {
                "paper_mode": paper_mode,
                "collection_enabled": collection_enabled,
                "acceptance_status": acceptance.status,
            },
            "health": health,
            "budget": budget_policy.to_dict(),
            "performance": performance,
            "alerts": alerts,
            "acceptance": {
                "acceptance_id": acceptance.acceptance_id,
                "policy_version": acceptance.policy_version,
                "criteria": acceptance.criteria,
                "integrity_anomalies": acceptance.integrity_anomalies,
                "latest_canary_id": acceptance.latest_canary_id,
            },
        }
