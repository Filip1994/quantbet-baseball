"""Railway worker entrypoint for the Baseball production runtime."""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .db import apply_migrations


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _record_activation_gate(
    root: Path,
    *,
    assessed_at: datetime,
    target: str = "CANARY",
) -> dict[str, object] | None:
    if not os.getenv("DATABASE_URL", "").strip():
        return None

    from .activation_gate import assess_activation_gate

    assessment = assess_activation_gate(
        root,
        target=target,
        now=assessed_at,
    )
    return {
        "assessment_id": assessment["assessment_id"],
        "target": assessment["target"],
        "verdict": assessment["verdict"],
        "reason_codes": assessment["reason_codes"],
        "budget": assessment["budget"],
        "checks": assessment["checks"],
    }


def _run_armed_canary(
    root: Path,
    *,
    started_at: datetime,
    activation_gate: dict[str, object] | None,
) -> dict[str, object]:
    """Run at most one bounded canary while a recent PASSED canary is absent."""

    if activation_gate is None:
        return {
            "status": "BLOCKED",
            "reason_codes": ["DATABASE_URL_MISSING"],
        }

    if activation_gate.get("verdict") != "READY":
        return {
            "status": "BLOCKED",
            "reason_codes": list(activation_gate.get("reason_codes") or ()),
        }

    checks = activation_gate.get("checks")
    if not isinstance(checks, dict):
        return {
            "status": "BLOCKED",
            "reason_codes": ["ACTIVATION_GATE_CHECKS_INVALID"],
        }

    if bool(checks.get("canary_passed")):
        return {
            "status": "ALREADY_PASSED",
            "canary_id": checks.get("latest_canary_id"),
            "reason_codes": [],
        }

    from .canary import run_canary_once

    return dict(run_canary_once(root, now=started_at))


def _record_runtime(
    result: dict[str, object],
    *,
    started_at: datetime,
    collection_enabled: bool,
) -> dict[str, object] | None:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        return None

    import psycopg

    from .postgres_repository import PostgreSQLEvidenceRepository

    finished_at = datetime.now(UTC)
    with psycopg.connect(database_url) as connection:
        repository = PostgreSQLEvidenceRepository(connection)
        repository.append_runtime_cycle(
            run_id=str(uuid.uuid4()),
            started_at=started_at,
            finished_at=finished_at,
            collection_enabled=collection_enabled,
            mode=str(result["mode"]),
            status=str(result["status"]),
            stats=dict(
                result.get("collection")
                or result.get("provider_surface_audit")
                or result.get("games_schema_audit")
                or {}
            ),
        )
        return repository.health_snapshot()


def run_once(root: Path | None = None) -> dict[str, object]:
    """Apply migrations, execute one bounded cycle, and expose canonical health."""

    started_at = datetime.now(UTC)
    project_root = root or Path.cwd()
    applied = apply_migrations(project_root)
    collection_enabled = _enabled("BASEBALL_ENABLE_COLLECTION")
    canary_enabled = _enabled("BASEBALL_ENABLE_CANARY")
    games_schema_audit_id = os.getenv("BASEBALL_GAMES_SCHEMA_AUDIT_ID", "").strip()
    games_schema_audit_date = os.getenv(
        "BASEBALL_GAMES_SCHEMA_AUDIT_DATE",
        started_at.date().isoformat(),
    ).strip()
    provider_surface_audit_id = os.getenv(
        "BASEBALL_PROVIDER_SURFACE_AUDIT_ID",
        "",
    ).strip()
    provider_surface_audit_season = int(
        os.getenv("BASEBALL_PROVIDER_SURFACE_AUDIT_SEASON", "2026")
    )

    result: dict[str, object] = {
        "status": "ready",
        "migrations_applied": list(applied),
        "collection_enabled": collection_enabled,
        "canary_enabled": canary_enabled,
        "games_schema_audit_armed": bool(games_schema_audit_id),
        "provider_surface_audit_armed": bool(provider_surface_audit_id),
    }

    # Fail closed if both paths are armed. A canary must never coexist with
    # scheduled collection.
    if collection_enabled and canary_enabled:
        result["mode"] = "storage-ready"
        result["status"] = "blocked"
        result["canary"] = {
            "status": "BLOCKED",
            "reason_codes": ["COLLECTION_AND_CANARY_CONFLICT"],
        }
    elif not collection_enabled:
        result["mode"] = "storage-ready"
        if games_schema_audit_id and not canary_enabled:
            from .games_schema_audit import run_games_schema_audit

            audit = run_games_schema_audit(
                project_root,
                audit_id=games_schema_audit_id,
                date_iso=games_schema_audit_date,
            )
            result["games_schema_audit"] = audit
            if audit.get("status") not in {"COMPLETE", "ALREADY_DONE"}:
                result["status"] = "audit-failed"

        if provider_surface_audit_id and not canary_enabled:
            from .provider_surface_audit import run_provider_surface_audit

            audit = run_provider_surface_audit(
                project_root,
                audit_id=provider_surface_audit_id,
                season=provider_surface_audit_season,
            )
            result["provider_surface_audit"] = audit
            if audit.get("status") not in {"COMPLETE", "ALREADY_DONE"}:
                result["status"] = "audit-failed"

        activation_gate = _record_activation_gate(
            project_root,
            assessed_at=started_at,
            target="CANARY",
        )
        if activation_gate is not None:
            result["activation_gate"] = activation_gate

        if canary_enabled:
            canary = _run_armed_canary(
                project_root,
                started_at=started_at,
                activation_gate=activation_gate,
            )
            result["canary"] = canary
            if canary.get("status") == "FAILED":
                result["status"] = "canary-failed"
            elif canary.get("status") == "BLOCKED":
                result["status"] = "blocked"

            if canary.get("status") in {"PASSED", "ALREADY_PASSED"}:
                scheduled_gate = _record_activation_gate(
                    project_root,
                    assessed_at=datetime.now(UTC),
                    target="SCHEDULED_COLLECTION",
                )
                if scheduled_gate is not None:
                    result["scheduled_collection_gate"] = scheduled_gate
    else:
        from .durable_collector import collect_durable_once

        result["mode"] = "collection"
        result["collection"] = collect_durable_once(project_root)

    health = _record_runtime(
        result,
        started_at=started_at,
        collection_enabled=collection_enabled,
    )
    if health is not None:
        result["health"] = health

    return result


def main() -> None:
    print(json.dumps(run_once(), sort_keys=True))


if __name__ == "__main__":
    main()
