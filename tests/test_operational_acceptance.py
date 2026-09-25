from quantbot.baseball.operational_acceptance import (
    build_activation_gate_assessment,
    build_budget_projection,
    build_canary_fact,
)


def test_75_request_cycle_cap_preserves_daily_reserve() -> None:
    budget = build_budget_projection(
        daily_request_budget=7500,
        cycle_request_cap=75,
        cron_interval_minutes=15,
        daily_reserve_required=250,
    )

    assert budget.cycles_per_day == 96
    assert budget.worst_case_daily_requests == 7200
    assert budget.request_headroom == 300
    assert budget.safe is True


def test_78_request_cycle_cap_is_blocked_by_reserve_rule() -> None:
    budget = build_budget_projection(
        daily_request_budget=7500,
        cycle_request_cap=78,
        cron_interval_minutes=15,
        daily_reserve_required=250,
    )

    assert budget.worst_case_daily_requests == 7488
    assert budget.request_headroom == 12
    assert budget.safe is False


def test_canary_gate_does_not_require_prior_canary() -> None:
    budget = build_budget_projection(
        daily_request_budget=7500,
        cycle_request_cap=75,
        cron_interval_minutes=15,
        daily_reserve_required=250,
    )
    assessment = build_activation_gate_assessment(
        target="CANARY",
        assessed_at="2026-09-25T16:00:00+00:00",
        budget=budget,
        paper_mode=True,
        collection_enabled=False,
        api_key_configured=True,
        raw_archive_configured=True,
        migrations_current=True,
        runtime_fresh=True,
        canary_passed=False,
        latest_canary_id=None,
    )

    assert assessment.verdict == "READY"
    assert assessment.reason_codes == ()


def test_scheduled_collection_requires_successful_canary() -> None:
    budget = build_budget_projection(
        daily_request_budget=7500,
        cycle_request_cap=75,
        cron_interval_minutes=15,
        daily_reserve_required=250,
    )
    assessment = build_activation_gate_assessment(
        target="SCHEDULED_COLLECTION",
        assessed_at="2026-09-25T16:00:00+00:00",
        budget=budget,
        paper_mode=True,
        collection_enabled=False,
        api_key_configured=True,
        raw_archive_configured=True,
        migrations_current=True,
        runtime_fresh=True,
        canary_passed=False,
        latest_canary_id=None,
    )

    assert assessment.verdict == "BLOCKED"
    assert assessment.reason_codes == ("CANARY_NOT_PASSED",)


def test_gate_blocks_if_scheduled_collection_is_already_enabled() -> None:
    budget = build_budget_projection(
        daily_request_budget=7500,
        cycle_request_cap=75,
        cron_interval_minutes=15,
        daily_reserve_required=250,
    )
    assessment = build_activation_gate_assessment(
        target="CANARY",
        assessed_at="2026-09-25T16:00:00+00:00",
        budget=budget,
        paper_mode=True,
        collection_enabled=True,
        api_key_configured=True,
        raw_archive_configured=True,
        migrations_current=True,
        runtime_fresh=True,
        canary_passed=False,
        latest_canary_id=None,
    )

    assert assessment.verdict == "BLOCKED"
    assert assessment.reason_codes == ("SCHEDULED_COLLECTION_ALREADY_ENABLED",)


def test_passed_canary_fact_requires_archive_and_database_evidence() -> None:
    fact = build_canary_fact(
        cycle_id="11111111-1111-1111-1111-111111111111",
        started_at="2026-09-25T16:00:00+00:00",
        finished_at="2026-09-25T16:01:00+00:00",
        status="PASSED",
        max_api_requests=8,
        api_requests=4,
        fixture_observations_inserted=2,
        observations_inserted=2,
        errors=0,
        archive_verified=True,
        db_write_verified=True,
        reason_codes=(),
    )

    assert fact.status == "PASSED"
    assert fact.reason_codes == ()
