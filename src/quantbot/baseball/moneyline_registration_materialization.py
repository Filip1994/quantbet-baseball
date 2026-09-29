"""Bounded runtime materialization for final Moneyline verification and paper picks."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from .decision_lifecycle import MoneylineEvaluation
from .evidence import EvidenceError
from .moneyline_registration import (
    MoneylineDecisionPolicy,
    RegistrationResult,
    verify_and_register_moneyline,
)


class RegistrationRepository(Protocol):
    def due_preliminary_candidates_for_registration(
        self,
        *,
        as_of: datetime,
        horizon_minutes: int,
        limit: int,
    ) -> tuple[MoneylineEvaluation, ...]: ...


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)


def _request_count(client: Any) -> int:
    value = getattr(client, "request_count", 0)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def materialize_due_moneyline_registrations(
    client: Any,
    repository: RegistrationRepository,
    *,
    now: datetime,
    horizon_minutes: int = 360,
    max_candidates: int = 1,
    policy: MoneylineDecisionPolicy | None = None,
    clock: Callable[[], datetime] | None = None,
    register: Callable[..., RegistrationResult] = verify_and_register_moneyline,
) -> dict[str, int | str]:
    """Verify and register a bounded number of due preliminary candidates."""

    if horizon_minutes < 1:
        raise ValueError("horizon_minutes must be positive")
    if max_candidates < 1:
        raise ValueError("max_candidates must be positive")

    current = _utc(now)
    active_policy = policy or MoneylineDecisionPolicy()
    candidates = repository.due_preliminary_candidates_for_registration(
        as_of=current,
        horizon_minutes=horizon_minutes,
        limit=max_candidates,
    )
    result: dict[str, int | str] = {
        "status": "NO_DUE_CANDIDATES",
        "candidates_seen": len(candidates),
        "candidates_considered": 0,
        "verifications_ready": 0,
        "verifications_rejected": 0,
        "picks_registered": 0,
        "registration_failures": 0,
        "provider_calls": 0,
    }
    if not candidates:
        return result

    before_calls = _request_count(client)
    runtime_clock = clock or (lambda: datetime.now(UTC))

    for candidate in candidates:
        result["candidates_considered"] = int(result["candidates_considered"]) + 1
        try:
            registration = register(
                client,
                repository,
                candidate.evaluation_id,
                clock=runtime_clock,
                policy=active_policy,
            )
        except (EvidenceError, LookupError, RuntimeError, TypeError, ValueError):
            result["registration_failures"] = int(result["registration_failures"]) + 1
            continue

        if registration.verification.status == "READY":
            result["verifications_ready"] = int(result["verifications_ready"]) + 1
            if registration.pick is not None:
                result["picks_registered"] = int(result["picks_registered"]) + 1
        elif registration.verification.status == "REJECTED":
            result["verifications_rejected"] = int(result["verifications_rejected"]) + 1
        else:
            result["registration_failures"] = int(result["registration_failures"]) + 1

    result["provider_calls"] = max(0, _request_count(client) - before_calls)
    if int(result["registration_failures"]) > 0:
        result["status"] = "BLOCKED_REGISTRATION"
    else:
        result["status"] = "COMPLETE"
    return result
