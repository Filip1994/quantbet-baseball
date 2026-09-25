"""Machine-readable activation gate for QuantBet Baseball."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg

from .config import BaseballSettings
from .db import database_url_from_env
from .operational_acceptance import (
    build_activation_gate_assessment,
    build_budget_projection,
)
from .operational_repository import PostgreSQLOperationalAcceptanceRepository

_RAW_ARCHIVE_ENV = (
    "BASEBALL_RAW_BUCKET",
    "BASEBALL_RAW_REGION",
    "BASEBALL_RAW_ENDPOINT",
    "BASEBALL_RAW_ACCESS_KEY_ID",
    "BASEBALL_RAW_SECRET_ACCESS_KEY",
)


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _raw_archive_configured() -> bool:
    return all(os.getenv(name, "").strip() for name in _RAW_ARCHIVE_ENV)


def assess_activation_gate(
    root: Path | None = None,
    *,
    target: str = "CANARY",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Persist and return a pre-activation readiness assessment."""

    project_root = root or Path.cwd()
    current = (now or datetime.now(UTC)).astimezone(UTC)
    settings = BaseballSettings.from_env(project_root)
    settings.validate()

    cycle_request_cap = int(
        os.getenv("BASEBALL_MAX_API_REQUESTS_PER_CYCLE", "75")
    )
    cron_interval_minutes = int(
        os.getenv("BASEBALL_CRON_INTERVAL_MINUTES", "15")
    )
    daily_reserve_required = int(
        os.getenv("BASEBALL_API_DAILY_RESERVE", "250")
    )
    runtime_max_age_minutes = int(
        os.getenv("BASEBALL_RUNTIME_MAX_AGE_MINUTES", "45")
    )
    canary_max_age_hours = int(
        os.getenv("BASEBALL_CANARY_MAX_AGE_HOURS", "24")
    )

    budget = build_budget_projection(
        daily_request_budget=settings.api_request_budget,
        cycle_request_cap=cycle_request_cap,
        cron_interval_minutes=cron_interval_minutes,
        daily_reserve_required=daily_reserve_required,
    )

    with psycopg.connect(database_url_from_env()) as connection:
        repository = PostgreSQLOperationalAcceptanceRepository(connection)
        migrations_current = repository.migrations_current(project_root)
        runtime_fresh = repository.runtime_fresh(
            as_of=current,
            max_age=timedelta(minutes=runtime_max_age_minutes),
        )
        canary_passed, latest_canary = repository.canary_passed_recently(
            as_of=current,
            max_age=timedelta(hours=canary_max_age_hours),
        )

        assessment = build_activation_gate_assessment(
            target=target,
            assessed_at=current.isoformat(),
            budget=budget,
            paper_mode=settings.paper_mode,
            collection_enabled=_enabled("BASEBALL_ENABLE_COLLECTION"),
            api_key_configured=bool(settings.api_key),
            raw_archive_configured=_raw_archive_configured(),
            migrations_current=migrations_current,
            runtime_fresh=runtime_fresh,
            canary_passed=canary_passed,
            latest_canary_id=(
                None if latest_canary is None else latest_canary.canary_id
            ),
        )
        repository.append_assessment(assessment)
        performance = repository.performance_snapshot()
        breakdown = repository.performance_breakdown()

    return {
        "assessment_id": assessment.assessment_id,
        "target": assessment.target,
        "verdict": assessment.verdict,
        "reason_codes": list(assessment.reason_codes),
        "budget": {
            "daily_request_budget": assessment.daily_request_budget,
            "cycle_request_cap": assessment.cycle_request_cap,
            "cron_interval_minutes": assessment.cron_interval_minutes,
            "cycles_per_day": assessment.cycles_per_day,
            "worst_case_daily_requests": assessment.worst_case_daily_requests,
            "request_headroom": assessment.request_headroom,
            "daily_reserve_required": assessment.daily_reserve_required,
        },
        "checks": {
            "paper_mode": assessment.paper_mode,
            "collection_enabled": assessment.collection_enabled,
            "api_key_configured": assessment.api_key_configured,
            "raw_archive_configured": assessment.raw_archive_configured,
            "migrations_current": assessment.migrations_current,
            "runtime_fresh": assessment.runtime_fresh,
            "canary_passed": assessment.canary_passed,
            "latest_canary_id": assessment.latest_canary_id,
        },
        "performance": performance,
        "performance_breakdown": list(breakdown),
    }


def main() -> None:
    target = os.getenv("BASEBALL_ACTIVATION_TARGET", "CANARY")
    print(json.dumps(assess_activation_gate(target=target), sort_keys=True))


if __name__ == "__main__":
    main()
