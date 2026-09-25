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
) -> dict[str, object] | None:
    if not os.getenv("DATABASE_URL", "").strip():
        return None

    from .activation_gate import assess_activation_gate

    assessment = assess_activation_gate(
        root,
        target="CANARY",
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
            stats=dict(result.get("collection") or {}),
        )
        return repository.health_snapshot()


def run_once(root: Path | None = None) -> dict[str, object]:
    """Apply migrations, execute one bounded cycle, and expose canonical health."""

    started_at = datetime.now(UTC)
    project_root = root or Path.cwd()
    applied = apply_migrations(project_root)
    collection_enabled = _enabled("BASEBALL_ENABLE_COLLECTION")

    result: dict[str, object] = {
        "status": "ready",
        "migrations_applied": list(applied),
        "collection_enabled": collection_enabled,
    }

    if not collection_enabled:
        result["mode"] = "storage-ready"
        activation_gate = _record_activation_gate(
            project_root,
            assessed_at=started_at,
        )
        if activation_gate is not None:
            result["activation_gate"] = activation_gate
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
