from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from quantbot.baseball.budget_policy import BaseballAPIBudgetPolicy
from quantbot.baseball.config import BaseballSettings
from quantbot.baseball.db import database_url_from_env
from quantbot.baseball.operational_repository import PostgreSQLOperationalRepository


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    root = Path(".")
    now = datetime.now(UTC)
    settings = BaseballSettings.from_env(root)
    budget = BaseballAPIBudgetPolicy.from_env(
        daily_limit=settings.api_request_budget
    )

    with psycopg.connect(database_url_from_env()) as connection:
        repository = PostgreSQLOperationalRepository(connection)
        payload = {
            "dashboard": repository.dashboard_snapshot(
                as_of=now,
                budget_policy=budget,
                paper_mode=settings.paper_mode,
                collection_enabled=_enabled("BASEBALL_ENABLE_COLLECTION"),
            ),
            "bulletin": repository.daily_bulletin(as_of=now),
        }

    print(json.dumps(payload, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
