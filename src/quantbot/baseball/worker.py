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
