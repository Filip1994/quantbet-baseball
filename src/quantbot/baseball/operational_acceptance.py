"""Operational canary and production-activation evidence for Baseball."""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from .evidence import EvidenceError

_CANARY_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/operational-canary/v1",
)
_GATE_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/activation-gate/v1",
)


def _timestamp(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise EvidenceError(f"{field} must be a non-empty ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise EvidenceError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{field} must be timezone-aware")
    return parsed


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise EvidenceError(f"{field} must be a positive integer")
    return value


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvidenceError(f"{field} must be a non-negative integer")
    return value


def _uuid(namespace: uuid.UUID, identity: dict[str, Any]) -> str:
    canonical = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return str(uuid.uuid5(namespace, canonical))


@dataclass(frozen=True, slots=True)
class BudgetProjection:
    daily_request_budget: int
    cycle_request_cap: int
    cron_interval_minutes: int
    cycles_per_day: int
    worst_case_daily_requests: int
    request_headroom: int
    daily_reserve_required: int

    def __post_init__(self) -> None:
        _positive_int(self.daily_request_budget, "daily_request_budget")
        _positive_int(self.cycle_request_cap, "cycle_request_cap")
        _positive_int(self.cron_interval_minutes, "cron_interval_minutes")
        _positive_int(self.cycles_per_day, "cycles_per_day")
        _nonnegative_int(
            self.worst_case_daily_requests,
            "worst_case_daily_requests",
        )
        _nonnegative_int(
            self.daily_reserve_required,
            "daily_reserve_required",
        )
        _nonnegative_int(self.daily_reserve_required, "daily_reserve_required")

    @property
    def safe(self) -> bool:
        return (
            self.worst_case_daily_requests <= self.daily_request_budget
            and self.request_headroom >= self.daily_reserve_required
        )


def build_budget_projection(
    *,
    daily_request_budget: int,
    cycle_request_cap: int,
    cron_interval_minutes: int,
    daily_reserve_required: int = 250,
) -> BudgetProjection:
    if cron_interval_minutes > 1440:
        raise EvidenceError("cron_interval_minutes cannot exceed one day")
    cycles_per_day = math.ceil(1440 / cron_interval_minutes)
    worst_case = cycle_request_cap * cycles_per_day
    return BudgetProjection(
        daily_request_budget=daily_request_budget,
        cycle_request_cap=cycle_request_cap,
        cron_interval_minutes=cron_interval_minutes,
        cycles_per_day=cycles_per_day,
        worst_case_daily_requests=worst_case,
        request_headroom=daily_request_budget - worst_case,
        daily_reserve_required=daily_reserve_required,
    )


@dataclass(frozen=True, slots=True)
class CanaryRunFact:
    canary_id: str
    cycle_id: str | None
    started_at: str
    finished_at: str
    status: str
    max_api_requests: int
    api_requests: int
    fixture_observations_inserted: int
    observations_inserted: int
    errors: int
    archive_verified: bool
    db_write_verified: bool
    reason_codes: tuple[str, ...]
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if not self.canary_id:
            raise EvidenceError("canary_id must be non-empty")
        started = _timestamp(self.started_at, "started_at")
        finished = _timestamp(self.finished_at, "finished_at")
        if finished < started:
            raise EvidenceError("canary cannot finish before it starts")
        if self.status not in {"PASSED", "FAILED", "SKIPPED_LOCKED"}:
            raise EvidenceError("unsupported canary status")
        _positive_int(self.max_api_requests, "max_api_requests")
        _nonnegative_int(self.api_requests, "api_requests")
        _nonnegative_int(
            self.fixture_observations_inserted,
            "fixture_observations_inserted",
        )
        _nonnegative_int(self.observations_inserted, "observations_inserted")
        _nonnegative_int(self.errors, "errors")
        if self.api_requests > self.max_api_requests:
            raise EvidenceError("canary exceeded max_api_requests")
        if self.status == "PASSED":
            if self.cycle_id is None:
                raise EvidenceError("passed canary requires cycle_id")
            if (
                self.errors != 0
                or not self.archive_verified
                or not self.db_write_verified
                or self.reason_codes
            ):
                raise EvidenceError("passed canary evidence is inconsistent")
        elif not self.reason_codes:
            raise EvidenceError("non-passed canary requires reason codes")


def build_canary_fact(
    *,
    cycle_id: str | None,
    started_at: str,
    finished_at: str,
    status: str,
    max_api_requests: int,
    api_requests: int,
    fixture_observations_inserted: int,
    observations_inserted: int,
    errors: int,
    archive_verified: bool,
    db_write_verified: bool,
    reason_codes: tuple[str, ...],
) -> CanaryRunFact:
    identity = {
        "cycle_id": cycle_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "max_api_requests": max_api_requests,
        "api_requests": api_requests,
        "fixture_observations_inserted": fixture_observations_inserted,
        "observations_inserted": observations_inserted,
        "errors": errors,
        "archive_verified": archive_verified,
        "db_write_verified": db_write_verified,
        "reason_codes": reason_codes,
    }
    return CanaryRunFact(
        canary_id=_uuid(_CANARY_NAMESPACE, identity),
        **identity,
    )


@dataclass(frozen=True, slots=True)
class ActivationGateAssessment:
    assessment_id: str
    target: str
    assessed_at: str
    verdict: str
    reason_codes: tuple[str, ...]
    daily_request_budget: int
    cycle_request_cap: int
    cron_interval_minutes: int
    cycles_per_day: int
    worst_case_daily_requests: int
    request_headroom: int
    daily_reserve_required: int
    paper_mode: bool
    collection_enabled: bool
    api_key_configured: bool
    raw_archive_configured: bool
    migrations_current: bool
    runtime_fresh: bool
    canary_passed: bool
    latest_canary_id: str | None
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if not self.assessment_id:
            raise EvidenceError("assessment_id must be non-empty")
        if self.target not in {"CANARY", "SCHEDULED_COLLECTION"}:
            raise EvidenceError("unsupported activation target")
        _timestamp(self.assessed_at, "assessed_at")
        if self.verdict not in {"READY", "BLOCKED"}:
            raise EvidenceError("unsupported gate verdict")
        if self.verdict == "READY" and self.reason_codes:
            raise EvidenceError("ready gate cannot have reason codes")
        if self.verdict == "BLOCKED" and not self.reason_codes:
            raise EvidenceError("blocked gate requires reason codes")
        _positive_int(self.daily_request_budget, "daily_request_budget")
        _positive_int(self.cycle_request_cap, "cycle_request_cap")
        _positive_int(self.cron_interval_minutes, "cron_interval_minutes")
        _positive_int(self.cycles_per_day, "cycles_per_day")
        _nonnegative_int(
            self.worst_case_daily_requests,
            "worst_case_daily_requests",
        )


def build_activation_gate_assessment(
    *,
    target: str,
    assessed_at: str,
    budget: BudgetProjection,
    paper_mode: bool,
    collection_enabled: bool,
    api_key_configured: bool,
    raw_archive_configured: bool,
    migrations_current: bool,
    runtime_fresh: bool,
    canary_passed: bool,
    latest_canary_id: str | None,
) -> ActivationGateAssessment:
    normalized_target = target.strip().upper()
    reasons: list[str] = []
    if not paper_mode:
        reasons.append("PAPER_MODE_REQUIRED")
    if collection_enabled:
        reasons.append("SCHEDULED_COLLECTION_ALREADY_ENABLED")
    if not api_key_configured:
        reasons.append("API_KEY_MISSING")
    if not raw_archive_configured:
        reasons.append("RAW_ARCHIVE_INCOMPLETE")
    if not migrations_current:
        reasons.append("MIGRATIONS_NOT_CURRENT")
    if not runtime_fresh:
        reasons.append("RUNTIME_STALE")
    if not budget.safe:
        reasons.append("API_BUDGET_UNSAFE")
    if normalized_target == "SCHEDULED_COLLECTION" and not canary_passed:
        reasons.append("CANARY_NOT_PASSED")

    reason_codes = tuple(sorted(set(reasons)))
    verdict = "READY" if not reason_codes else "BLOCKED"
    identity = {
        "target": normalized_target,
        "assessed_at": assessed_at,
        "verdict": verdict,
        "reason_codes": reason_codes,
        "daily_request_budget": budget.daily_request_budget,
        "cycle_request_cap": budget.cycle_request_cap,
        "cron_interval_minutes": budget.cron_interval_minutes,
        "cycles_per_day": budget.cycles_per_day,
        "worst_case_daily_requests": budget.worst_case_daily_requests,
        "request_headroom": budget.request_headroom,
        "daily_reserve_required": budget.daily_reserve_required,
        "paper_mode": paper_mode,
        "collection_enabled": collection_enabled,
        "api_key_configured": api_key_configured,
        "raw_archive_configured": raw_archive_configured,
        "migrations_current": migrations_current,
        "runtime_fresh": runtime_fresh,
        "canary_passed": canary_passed,
        "latest_canary_id": latest_canary_id,
    }
    return ActivationGateAssessment(
        assessment_id=_uuid(_GATE_NAMESPACE, identity),
        **identity,
    )


def canonical_operational_json(
    record: CanaryRunFact | ActivationGateAssessment,
) -> str:
    return json.dumps(
        asdict(record),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
