"""Explicitly armed, bounded production canary for Baseball collection."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from .db import database_url_from_env
from .durable_collector import collect_durable_once
from .operational_product import build_canary_run
from .operational_repository import PostgreSQLOperationalRepository
from .raw_archive import archive_from_env


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def run_controlled_canary(
    root: Path,
    *,
    now: datetime | None = None,
    max_api_requests: int = 12,
    max_odds_requests: int = 4,
    archive_sample_limit: int = 20,
) -> dict[str, object]:
    """Run one small paper collector cycle and persist its acceptance fact."""

    if not _enabled("BASEBALL_ALLOW_CANARY"):
        raise RuntimeError("BASEBALL_ALLOW_CANARY=true is required for a canary run")
    if max_api_requests < 1:
        raise ValueError("max_api_requests must be positive")
    if max_odds_requests < 1:
        raise ValueError("max_odds_requests must be positive")
    if archive_sample_limit < 1:
        raise ValueError("archive_sample_limit must be positive")

    started_at = datetime.now(UTC)
    summary = collect_durable_once(
        root,
        now=now or started_at,
        request_limit=max_api_requests,
        max_odds_requests_override=max_odds_requests,
    )
    finished_at = datetime.now(UTC)

    archive = archive_from_env(root / "data" / "baseball" / "raw_api", require_remote=True)
    verified = 0
    failures = 0

    with psycopg.connect(database_url_from_env()) as connection:
        repository = PostgreSQLOperationalRepository(connection)
        evidence = repository.archive_evidence_sample(
            observed_after=started_at,
            limit=archive_sample_limit,
        )
        for ref, checksum in evidence:
            if archive.verify(ref, checksum):
                verified += 1
            else:
                failures += 1

        canary_summary = dict(summary)
        canary_summary["archive_objects_verified"] = verified
        canary_summary["archive_verification_failures"] = failures
        record = build_canary_run(
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            max_api_requests=max_api_requests,
            max_odds_requests=max_odds_requests,
            summary=canary_summary,
        )
        repository.append_canary(record)

    return {
        "canary_id": record.canary_id,
        "passed": record.passed,
        "reason_codes": list(record.reason_codes),
        "max_api_requests": max_api_requests,
        "max_odds_requests": max_odds_requests,
        "api_requests": record.api_requests,
        "fixture_observations_inserted": record.fixture_observations_inserted,
        "observations_inserted": record.observations_inserted,
        "archive_objects_verified": record.archive_objects_verified,
        "archive_verification_failures": record.archive_verification_failures,
        "errors": record.errors,
    }
