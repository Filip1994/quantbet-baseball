from pathlib import Path

import pytest

from quantbot.baseball import worker


@pytest.fixture(autouse=True)
def _clean_runtime_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASEBALL_ENABLE_COLLECTION", "false")
    monkeypatch.setenv("BASEBALL_ENABLE_CANARY", "false")
    monkeypatch.setenv("DATABASE_URL", "postgresql://example.invalid/db")
    monkeypatch.setattr(worker, "apply_migrations", lambda _root: ())
    monkeypatch.setattr(worker, "_record_runtime", lambda *_args, **_kwargs: None)


def _ready_gate(*, canary_passed: bool = False) -> dict[str, object]:
    return {
        "assessment_id": "gate-1",
        "target": "CANARY",
        "verdict": "READY",
        "reason_codes": [],
        "budget": {
            "daily_request_budget": 7500,
            "cycle_request_cap": 75,
            "cron_interval_minutes": 15,
            "cycles_per_day": 96,
            "worst_case_daily_requests": 7200,
            "request_headroom": 300,
            "daily_reserve_required": 250,
        },
        "checks": {
            "paper_mode": True,
            "collection_enabled": False,
            "api_key_configured": True,
            "raw_archive_configured": True,
            "migrations_current": True,
            "runtime_fresh": True,
            "canary_passed": canary_passed,
            "latest_canary_id": "canary-1" if canary_passed else None,
        },
    }


def test_storage_ready_worker_does_not_run_canary_when_not_armed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        worker,
        "_record_activation_gate",
        lambda *_args, **_kwargs: _ready_gate(),
    )

    result = worker.run_once(Path("."))

    assert result["mode"] == "storage-ready"
    assert result["status"] == "ready"
    assert result["canary_enabled"] is False
    assert "canary" not in result


def test_armed_canary_runs_once_when_gate_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BASEBALL_ENABLE_CANARY", "true")
    calls: list[str] = []

    def fake_gate(*_args: object, **kwargs: object) -> dict[str, object]:
        target = str(kwargs.get("target"))
        if target == "SCHEDULED_COLLECTION":
            return {
                **_ready_gate(canary_passed=True),
                "target": "SCHEDULED_COLLECTION",
            }
        return _ready_gate()

    monkeypatch.setattr(worker, "_record_activation_gate", fake_gate)

    import quantbot.baseball.canary as canary_module

    def fake_canary(_root: Path, *, now: object) -> dict[str, object]:
        calls.append("run")
        return {
            "status": "PASSED",
            "canary_id": "canary-1",
            "reason_codes": [],
            "summary": {"api_requests": 4},
        }

    monkeypatch.setattr(canary_module, "run_canary_once", fake_canary)

    result = worker.run_once(Path("."))

    assert calls == ["run"]
    assert result["mode"] == "storage-ready"
    assert result["status"] == "ready"
    assert result["canary"]["status"] == "PASSED"
    assert result["scheduled_collection_gate"]["target"] == "SCHEDULED_COLLECTION"


def test_recent_passed_canary_prevents_reexecution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BASEBALL_ENABLE_CANARY", "true")
    monkeypatch.setattr(
        worker,
        "_record_activation_gate",
        lambda *_args, **_kwargs: _ready_gate(canary_passed=True),
    )

    import quantbot.baseball.canary as canary_module

    def should_not_run(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("canary must not rerun after a recent PASSED fact")

    monkeypatch.setattr(canary_module, "run_canary_once", should_not_run)

    result = worker.run_once(Path("."))

    assert result["canary"]["status"] == "ALREADY_PASSED"
    assert result["canary"]["canary_id"] == "canary-1"


def test_armed_canary_stays_blocked_when_gate_is_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BASEBALL_ENABLE_CANARY", "true")
    gate = _ready_gate()
    gate["verdict"] = "BLOCKED"
    gate["reason_codes"] = ["API_KEY_MISSING"]
    monkeypatch.setattr(
        worker,
        "_record_activation_gate",
        lambda *_args, **_kwargs: gate,
    )

    result = worker.run_once(Path("."))

    assert result["status"] == "blocked"
    assert result["canary"] == {
        "status": "BLOCKED",
        "reason_codes": ["API_KEY_MISSING"],
    }


def test_collection_and_canary_conflict_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BASEBALL_ENABLE_COLLECTION", "true")
    monkeypatch.setenv("BASEBALL_ENABLE_CANARY", "true")

    result = worker.run_once(Path("."))

    assert result["mode"] == "storage-ready"
    assert result["status"] == "blocked"
    assert result["canary"]["reason_codes"] == ["COLLECTION_AND_CANARY_CONFLICT"]
