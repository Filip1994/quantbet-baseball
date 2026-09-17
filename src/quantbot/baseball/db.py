"""Minimal PostgreSQL migration runner for the Railway runtime."""
from __future__ import annotations

import os
from pathlib import Path

import psycopg


MIGRATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


def database_url_from_env() -> str:
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("DATABASE_URL is required")
    return value


def migration_files(root: Path) -> tuple[Path, ...]:
    return tuple(sorted((root / "migrations").glob("*.sql")))


def apply_migrations(root: Path, database_url: str | None = None) -> tuple[str, ...]:
    """Apply each migration exactly once and return newly applied versions."""
    url = database_url or database_url_from_env()
    applied: list[str] = []

    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(MIGRATION_TABLE_SQL)

        for path in migration_files(root):
            version = path.name
            already_applied = connection.execute(
                "SELECT 1 FROM schema_migrations WHERE version = %s",
                (version,),
            ).fetchone()
            if already_applied is not None:
                continue

            connection.execute(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)",
                (version,),
            )
            applied.append(version)

    return tuple(applied)
