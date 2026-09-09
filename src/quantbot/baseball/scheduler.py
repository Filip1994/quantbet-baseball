from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any


def observation_interval_minutes(kickoff: datetime, now: datetime) -> int:
    """Adaptive cadence chosen for Baseball's 15-minute production clock."""
    minutes_to_game = (kickoff - now).total_seconds() / 60.0
    if minutes_to_game > 24 * 60:
        return 120
    if minutes_to_game > 6 * 60:
        return 60
    if minutes_to_game > 3 * 60:
        return 30
    if minutes_to_game > 60:
        return 15
    if minutes_to_game > -180:
        return 15
    return 10_000


def is_observation_due(kickoff: datetime, now: datetime, last_captured_at: datetime | None) -> bool:
    if last_captured_at is None:
        return True
    interval = observation_interval_minutes(kickoff, now)
    return now - last_captured_at >= timedelta(minutes=interval)


def build_scheduler_record(game: dict[str, Any], now: datetime, last_captured_at: datetime | None) -> dict[str, Any]:
    kickoff = game["kickoff"]
    if isinstance(kickoff, str):
        kickoff = datetime.fromisoformat(kickoff)
    kickoff = kickoff.astimezone(UTC)
    interval = observation_interval_minutes(kickoff, now)
    due = is_observation_due(kickoff, now, last_captured_at)
    return {
        "event_id": str(game["game_id"]),
        "kickoff": kickoff.isoformat(),
        "minutes_to_kickoff": round((kickoff - now).total_seconds() / 60, 1),
        "cadence_minutes": interval,
        "last_observation_at": last_captured_at.isoformat() if last_captured_at else None,
        "observation_due": due,
        "priority": "CLOSING" if -180 < (kickoff - now).total_seconds() / 60 <= 60 else "ACTIVE",
    }
