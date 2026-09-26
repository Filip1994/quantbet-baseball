"""Standalone Railway entrypoint for QuantBet Baseball dashboard."""

from __future__ import annotations

import os
import signal
from threading import Event

from .dashboard import (
    BaseballDashboard,
    BaseballDashboardHTTPService,
    BaseballDashboardRepository,
)


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required dashboard configuration: {name}")
    return value


def _integer(name: str, default: str) -> int:
    try:
        return int(os.getenv(name, default).strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def main() -> None:
    database_url = _required("DATABASE_URL")
    repository = BaseballDashboardRepository(database_url)
    if not repository.check_database():
        raise RuntimeError("PostgreSQL is unavailable")
    dashboard = BaseballDashboard(repository)
    dashboard.snapshot()

    stop = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    service = BaseballDashboardHTTPService(
        dashboard,
        host="0.0.0.0",
        port=_integer("PORT", "8080"),
    )
    try:
        service.start()
        stop.wait()
    finally:
        service.close()


if __name__ == "__main__":
    main()
