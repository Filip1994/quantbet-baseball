"""Operational evidence contracts for fixtures and runtime telemetry."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from .collector import _game_id, _game_time, _league_name, _team_names
from .raw_archive import ArchiveReceipt

_FIXTURE_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/fixture-observation/v1",
)


def _status(game: dict[str, Any]) -> str:
    raw = game.get("status")
    if isinstance(raw, dict):
        raw = raw.get("short") or raw.get("long")
    if raw is None and isinstance(game.get("game"), dict):
        nested = game["game"].get("status")
        if isinstance(nested, dict):
            raw = nested.get("short") or nested.get("long")
        else:
            raw = nested
    value = str(raw or "UNKNOWN").strip()
    return value or "UNKNOWN"


def _uuid(identity: dict[str, Any]) -> str:
    canonical = json.dumps(
        identity,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return str(uuid.uuid5(_FIXTURE_NAMESPACE, canonical))


@dataclass(frozen=True, slots=True)
class FixtureObservation:
    fixture_observation_id: str
    game_id: str
    league: str
    home_team: str
    away_team: str
    kickoff_at: str
    provider_status: str
    observed_at: str
    source_payload_ref: str
    source_payload_checksum: str
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def fixture_observation_from_game(
    game: dict[str, Any],
    receipt: ArchiveReceipt,
) -> FixtureObservation | None:
    game_id = _game_id(game)
    kickoff = _game_time(game)
    home, away = _team_names(game)
    if game_id is None or kickoff is None or not home or not away:
        return None

    identity = {
        "game_id": str(game_id),
        "league": _league_name(game) or "UNKNOWN",
        "home_team": home,
        "away_team": away,
        "kickoff_at": kickoff.isoformat(),
        "provider_status": _status(game),
        "observed_at": receipt.captured_at,
        "source_payload_checksum": receipt.checksum,
    }
    return FixtureObservation(
        fixture_observation_id=_uuid(identity),
        game_id=str(game_id),
        league=identity["league"],
        home_team=home,
        away_team=away,
        kickoff_at=kickoff.isoformat(),
        provider_status=identity["provider_status"],
        observed_at=receipt.captured_at,
        source_payload_ref=receipt.ref,
        source_payload_checksum=receipt.checksum,
    )


def fixture_canonical_json(record: FixtureObservation) -> str:
    return json.dumps(
        record.to_dict(),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
