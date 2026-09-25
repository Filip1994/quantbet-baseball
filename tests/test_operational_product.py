from datetime import UTC, datetime

import pytest

from quantbot.baseball.budget_policy import BaseballAPIBudgetPolicy
from quantbot.baseball.operational_product import (
    AcceptanceCriterion,
    build_acceptance_run,
    build_canary_run,
)


def test_daily_budget_policy_derives_real_per_run_hard_cap() -> None:
    policy = BaseballAPIBudgetPolicy(
        daily_limit=7500,
        cron_interval_minutes=15,
        reserved_headroom=750,
    )

    assert policy.runs_per_day == 96
    assert policy.usable_daily_budget == 6750
    assert policy.per_run_hard_limit == 70
    assert policy.maximum_scheduled_daily_requests == 6720
    assert policy.effective_headroom == 780
    assert policy.budget_safe is True


def test_budget_policy_rejects_schedule_that_cannot_be_bounded() -> None:
    with pytest.raises(ValueError, match="usable daily budget"):
        BaseballAPIBudgetPolicy(
            daily_limit=50,
            cron_interval_minutes=15,
            reserved_headroom=10,
        )


def test_canary_requires_database_writes_and_archive_readback() -> None:
    record = build_canary_run(
        started_at="2026-09-25T14:00:00+00:00",
        finished_at="2026-09-25T14:00:10+00:00",
        max_api_requests=12,
        max_odds_requests=4,
        summary={
            "status": "collected",
            "api_requests": 6,
            "fixture_observations_inserted": 2,
            "observations_inserted": 4,
            "archive_objects_verified": 6,
            "archive_verification_failures": 0,
            "errors": 0,
        },
    )

    assert record.passed is True
    assert record.reason_codes == ()


def test_canary_fails_closed_without_archive_readback() -> None:
    record = build_canary_run(
        started_at="2026-09-25T14:00:00+00:00",
        finished_at="2026-09-25T14:00:10+00:00",
        max_api_requests=12,
        max_odds_requests=4,
        summary={
            "status": "collected",
            "api_requests": 6,
            "fixture_observations_inserted": 2,
            "observations_inserted": 4,
            "archive_objects_verified": 0,
            "archive_verification_failures": 0,
            "errors": 0,
        },
    )

    assert record.passed is False
    assert "NO_ARCHIVE_READBACK" in record.reason_codes


def test_acceptance_status_is_derived_only_from_all_criteria() -> None:
    policy = BaseballAPIBudgetPolicy()
    ready = build_acceptance_run(
        evaluated_at=datetime(2026, 9, 25, 14, 0, tzinfo=UTC).isoformat(),
        budget_policy=policy,
        criteria=(
            AcceptanceCriterion("PAPER_MODE", True, "paper"),
            AcceptanceCriterion("BOUNDED_CANARY", True, "passed"),
        ),
        integrity_anomalies=0,
        latest_canary_id="canary-1",
    )
    blocked = build_acceptance_run(
        evaluated_at=datetime(2026, 9, 25, 14, 1, tzinfo=UTC).isoformat(),
        budget_policy=policy,
        criteria=(
            AcceptanceCriterion("PAPER_MODE", True, "paper"),
            AcceptanceCriterion("BOUNDED_CANARY", False, "missing"),
        ),
        integrity_anomalies=0,
        latest_canary_id=None,
    )

    assert ready.status == "READY"
    assert blocked.status == "BLOCKED"
