"""Operational product contracts for the Baseball paper engine."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from .budget_policy import BaseballAPIBudgetPolicy
from .evidence import EvidenceError

_CANARY_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/collection-canary/v1",
)
_ACCEPTANCE_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/operational-acceptance/v1",
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


def _uuid(namespace: uuid.UUID, identity: dict[str, Any]) -> str:
    canonical = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return str(uuid.uuid5(namespace, canonical))


@dataclass(frozen=True, slots=True)
class CollectionCanaryRun:
    canary_id: str
    started_at: str
    finished_at: str
    max_api_requests: int
    max_odds_requests: int
    status: str
    api_requests: int
    fixture_observations_inserted: int
    observations_inserted: int
    archive_objects_verified: int
    archive_verification_failures: int
    errors: int
    passed: bool
    reason_codes: tuple[str, ...]
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        started = _timestamp(self.started_at, "started_at")
        finished = _timestamp(self.finished_at, "finished_at")
        if finished < started:
            raise EvidenceError("canary finished_at cannot precede started_at")
        if self.max_api_requests < 1 or self.max_odds_requests < 0:
            raise EvidenceError("canary limits are invalid")
        if self.status not in {"collected", "skipped_locked", "failed"}:
            raise EvidenceError("canary status is unsupported")
        for field in (
            "api_requests",
            "fixture_observations_inserted",
            "observations_inserted",
            "archive_objects_verified",
            "archive_verification_failures",
            "errors",
        ):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise EvidenceError(f"{field} must be a non-negative integer")
        if self.api_requests > self.max_api_requests:
            raise EvidenceError("canary exceeded its API request limit")
        expected_pass = (
            self.status == "collected"
            and self.errors == 0
            and self.fixture_observations_inserted > 0
            and self.observations_inserted > 0
            and self.archive_objects_verified > 0
            and self.archive_verification_failures == 0
        )
        if self.passed != expected_pass:
            raise EvidenceError("canary pass flag does not match evidence")
        if self.passed and self.reason_codes:
            raise EvidenceError("passed canary cannot contain reason codes")
        if not self.passed and not self.reason_codes:
            raise EvidenceError("failed canary requires reason codes")


@dataclass(frozen=True, slots=True)
class AcceptanceCriterion:
    code: str
    passed: bool
    detail: str

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.detail.strip():
            raise EvidenceError("acceptance criterion fields must be non-empty")


@dataclass(frozen=True, slots=True)
class OperationalAcceptanceRun:
    acceptance_id: str
    evaluated_at: str
    policy_version: str
    status: str
    criteria: dict[str, dict[str, Any]]
    budget: dict[str, Any]
    integrity_anomalies: int
    latest_canary_id: str | None
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        _timestamp(self.evaluated_at, "evaluated_at")
        if not self.policy_version.strip():
            raise EvidenceError("policy_version must be non-empty")
        if self.status not in {"READY", "BLOCKED"}:
            raise EvidenceError("acceptance status is unsupported")
        if self.integrity_anomalies < 0:
            raise EvidenceError("integrity_anomalies cannot be negative")
        if not self.criteria:
            raise EvidenceError("criteria must be non-empty")
        all_passed = all(bool(item.get("passed")) for item in self.criteria.values())
        if (self.status == "READY") != all_passed:
            raise EvidenceError("acceptance status does not match criteria")


def canonical_canary_json(record: CollectionCanaryRun) -> str:
    payload = asdict(record)
    payload["reason_codes"] = list(record.reason_codes)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def canonical_acceptance_json(record: OperationalAcceptanceRun) -> str:
    return json.dumps(
        asdict(record),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def build_canary_run(
    *,
    started_at: str,
    finished_at: str,
    max_api_requests: int,
    max_odds_requests: int,
    summary: dict[str, Any],
) -> CollectionCanaryRun:
    status = str(summary.get("status") or "failed")
    api_requests = int(summary.get("api_requests", 0))
    fixtures = int(summary.get("fixture_observations_inserted", 0))
    observations = int(summary.get("observations_inserted", 0))
    archive_objects_verified = int(summary.get("archive_objects_verified", 0))
    archive_verification_failures = int(
        summary.get("archive_verification_failures", 0)
    )
    errors = int(summary.get("errors", 0))
    reasons: list[str] = []
    if status != "collected":
        reasons.append(f"STATUS_{status.upper()}")
    if errors:
        reasons.append("COLLECTION_ERRORS")
    if fixtures <= 0:
        reasons.append("NO_FIXTURE_WRITES")
    if observations <= 0:
        reasons.append("NO_MONEYLINE_WRITES")
    if archive_objects_verified <= 0:
        reasons.append("NO_ARCHIVE_READBACK")
    if archive_verification_failures:
        reasons.append("ARCHIVE_READBACK_FAILED")
    if api_requests > max_api_requests:
        reasons.append("API_LIMIT_EXCEEDED")
    passed = not reasons
    identity = {
        "started_at": started_at,
        "finished_at": finished_at,
        "max_api_requests": max_api_requests,
        "max_odds_requests": max_odds_requests,
        "summary": summary,
    }
    return CollectionCanaryRun(
        canary_id=_uuid(_CANARY_NAMESPACE, identity),
        started_at=started_at,
        finished_at=finished_at,
        max_api_requests=max_api_requests,
        max_odds_requests=max_odds_requests,
        status=status if status in {"collected", "skipped_locked"} else "failed",
        api_requests=api_requests,
        fixture_observations_inserted=fixtures,
        observations_inserted=observations,
        archive_objects_verified=archive_objects_verified,
        archive_verification_failures=archive_verification_failures,
        errors=errors,
        passed=passed,
        reason_codes=tuple(reasons),
    )


def build_acceptance_run(
    *,
    evaluated_at: str,
    budget_policy: BaseballAPIBudgetPolicy,
    criteria: tuple[AcceptanceCriterion, ...],
    integrity_anomalies: int,
    latest_canary_id: str | None,
    policy_version: str = "BASEBALL_OPERATIONAL_ACCEPTANCE_V1",
) -> OperationalAcceptanceRun:
    criteria_payload = {
        item.code: {"passed": item.passed, "detail": item.detail} for item in criteria
    }
    status = "READY" if all(item.passed for item in criteria) else "BLOCKED"
    identity = {
        "evaluated_at": evaluated_at,
        "policy_version": policy_version,
        "criteria": criteria_payload,
        "budget": budget_policy.to_dict(),
        "integrity_anomalies": integrity_anomalies,
        "latest_canary_id": latest_canary_id,
    }
    return OperationalAcceptanceRun(
        acceptance_id=_uuid(_ACCEPTANCE_NAMESPACE, identity),
        evaluated_at=evaluated_at,
        policy_version=policy_version,
        status=status,
        criteria=criteria_payload,
        budget=budget_policy.to_dict(),
        integrity_anomalies=integrity_anomalies,
        latest_canary_id=latest_canary_id,
    )
