"""Railway worker entrypoint for the Baseball production runtime."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .db import apply_migrations


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def run_once(root: Path | None = None) -> dict[str, object]:
    """Apply migrations, then run one collection cycle when explicitly enabled."""

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
        return result

    from .durable_collector import collect_durable_once

    result["mode"] = "collection"
    result["collection"] = collect_durable_once(project_root)
    return result


def main() -> None:
    print(json.dumps(run_once(), sort_keys=True))


if __name__ == "__main__":
    main()
