"""Railway worker entrypoint for the Baseball production runtime."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .db import apply_migrations


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def run_once(root: Path | None = None) -> dict[str, object]:
    """Boot the durable runtime without enabling collection prematurely."""
    project_root = root or Path.cwd()
    applied = apply_migrations(project_root)

    result: dict[str, object] = {
        "status": "ready",
        "migrations_applied": list(applied),
        "collection_enabled": _enabled("BASEBALL_ENABLE_COLLECTION"),
    }

    if result["collection_enabled"]:
        raise RuntimeError(
            "BASEBALL_ENABLE_COLLECTION cannot be enabled until the canonical "
            "PostgreSQL ingestion path lands"
        )

    result["mode"] = "storage-ready"
    return result


def main() -> None:
    print(json.dumps(run_once(), sort_keys=True))


if __name__ == "__main__":
    main()
