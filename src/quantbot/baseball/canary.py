"""Bounded one-shot operational canary for QuantBet Baseball."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from .db import apply_migrations, database_url_from_env
from .durable_collector import collect_durable_once
from .operational_acceptance import build_canary_fact
from .operational_repository import PostgreSQLOperationalAcceptanceRepository


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def run_canary_once(
    root: Path | None = None,
    *,
    now: datetime | None = None,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """Run one bounded ingestion canary while scheduled collection remains disabled."""

    project_root = root or Path.cwd()
    current_time = clock or (lambda: datetime.now(UTC))

    if _enabled("BASEBALL_ENABLE_COLLECTION"):
        raise RuntimeError(
            "canary requires BASEBALL_ENABLE_COLLECTION to remain disabled"
        )
    if not _enabled("BASEBALL_ENABLE_CANARY"):
        raise RuntimeError("BASEBALL_ENABLE_CANARY must be explicitly enabled")

    max_api_requests = int(os.getenv("BASEBALL_CANARY_MAX_API_REQUESTS", "8"))
    max_odds_requests = int(os.getenv("BASEBALL_CANARY_MAX_ODDS_REQUESTS", "2"))
    max_monitoring_refreshes = int(
        os.getenv("BASEBALL_CANARY_MAX_MONITORING_REFRESHES", "1")
    )
    max_settlement_refreshes = int(
        os.getenv("BASEBALL_CANARY_MAX_SETTLEMENT_REFRESHES", "1")
    )
    for name, value in (
        ("BASEBALL_CANARY_MAX_API_REQUESTS", max_api_requests),
        ("BASEBALL_CANARY_MAX_ODDS_REQUESTS", max_odds_requests),
        ("BASEBALL_CANARY_MAX_MONITORING_REFRESHES", max_monitoring_refreshes),
        ("BASEBALL_CANARY_MAX_SETTLEMENT_REFRESHES", max_settlement_refreshes),
    ):
        if value < 1:
            raise ValueError(f"{name} must be positive")

    applied = apply_migrations(project_root)
    started_at = (now or current_time()).astimezone(UTC)

    try:
        summary = collect_durable_once(
            project_root,
            now=started_at,
            execution_mode="CANARY",
            max_api_requests_per_cycle=max_api_requests,
            max_odds_requests_override=max_odds_requests,
            max_monitoring_refreshes_override=max_monitoring_refreshes,
            max_settlement_refreshes_override=max_settlement_refreshes,
        )
        finished_at = current_time().astimezone(UTC)
        cycle_id = str(summary.get("cycle_id") or "") or None

        with psycopg.connect(database_url_from_env()) as connection:
            repository = PostgreSQLOperationalAcceptanceRepository(connection)
            if summary["status"] == "skipped_locked":
                evidence = {
                    "execution_mode": "CANARY",
                    "fixture_observations_inserted": 0,
                    "observations_inserted": 0,
                    "errors": 0,
                    "archive_verified": False,
                    "db_write_verified": False,
                }
                status = "SKIPPED_LOCKED"
                reasons = ("COLLECTOR_LOCKED",)
            elif cycle_id is None:
                evidence = {
                    "execution_mode": "UNKNOWN",
                    "fixture_observations_inserted": 0,
                    "observations_inserted": 0,
                    "errors": int(summary.get("errors", 0)),
                    "archive_verified": False,
                    "db_write_verified": False,
                }
                status = "FAILED"
                reasons = ("MISSING_COLLECTION_CYCLE_ID",)
            else:
                evidence = repository.verify_canary_cycle(cycle_id)
                reasons_list: list[str] = []
                if evidence["execution_mode"] != "CANARY":
                    reasons_list.append("WRONG_EXECUTION_MODE")
                if int(summary.get("api_requests", 0)) <= 0:
                    reasons_list.append("NO_PROVIDER_REQUESTS")
                if int(evidence["errors"]) > 0:
                    reasons_list.append("COLLECTION_ERRORS")
                if not bool(evidence["archive_verified"]):
                    reasons_list.append("RAW_ARCHIVE_NOT_VERIFIED")
                if not bool(evidence["db_write_verified"]):
                    reasons_list.append("POSTGRES_WRITES_NOT_VERIFIED")
                reasons = tuple(sorted(set(reasons_list)))
                status = "PASSED" if not reasons else "FAILED"

            fact = build_canary_fact(
                cycle_id=cycle_id,
                started_at=started_at.isoformat(),
                finished_at=finished_at.isoformat(),
                status=status,
                max_api_requests=max_api_requests,
                api_requests=int(summary.get("api_requests", 0)),
                fixture_observations_inserted=int(
                    evidence["fixture_observations_inserted"]
                ),
                observations_inserted=int(evidence["observations_inserted"]),
                errors=int(evidence["errors"]),
                archive_verified=bool(evidence["archive_verified"]),
                db_write_verified=bool(evidence["db_write_verified"]),
                reason_codes=reasons,
            )
            repository.append_canary(fact)

        return {
            "status": fact.status,
            "canary_id": fact.canary_id,
            "reason_codes": list(fact.reason_codes),
            "migrations_applied": list(applied),
            "summary": summary,
            "evidence": evidence,
        }
    except (RuntimeError, ValueError, psycopg.Error) as exc:
        finished_at = current_time().astimezone(UTC)
        reason = f"CANARY_EXCEPTION_{type(exc).__name__.upper()}"
        fact = build_canary_fact(
            cycle_id=None,
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            status="FAILED",
            max_api_requests=max_api_requests,
            api_requests=0,
            fixture_observations_inserted=0,
            observations_inserted=0,
            errors=1,
            archive_verified=False,
            db_write_verified=False,
            reason_codes=(reason,),
        )
        try:
            with psycopg.connect(database_url_from_env()) as connection:
                repository = PostgreSQLOperationalAcceptanceRepository(connection)
                repository.append_canary(fact)
        except psycopg.Error:
            raise exc
        return {
            "status": "FAILED",
            "canary_id": fact.canary_id,
            "reason_codes": [reason],
            "migrations_applied": list(applied),
        }


def main() -> None:
    print(json.dumps(run_canary_once(), sort_keys=True))


if __name__ == "__main__":
    main()
