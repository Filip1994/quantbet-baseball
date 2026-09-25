"""Canonical immutable fixture evidence for QuantBet Baseball."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from .evidence import EvidenceError
from .raw_archive import ArchiveReceipt

_PROVIDER = "api-sports-baseball"
_FIXTURE_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/fixture-observation/v1",
)


def _timestamp(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise EvidenceError(f"{field} must be a non-empty ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise EvidenceError(f"{field} is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{field} must be timezone-aware")
    return parsed


def _text(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise EvidenceError(f"{field} must be a non-empty string")
    return result


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise EvidenceError(f"{field} must be a positive integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field} must be a positive integer") from exc
    if result <= 0:
        raise EvidenceError(f"{field} must be a positive integer")
    return result


def _nested_game(game: dict[str, Any]) -> dict[str, Any]:
    nested = game.get("game")
    return nested if isinstance(nested, dict) else {}


def _game_value(game: dict[str, Any], key: str) -> Any:
    value = game.get(key)
    if value is not None:
        return value
    return _nested_game(game).get(key)


def _teams(game: dict[str, Any]) -> dict[str, Any]:
    value = game.get("teams") or _nested_game(game).get("teams")
    return value if isinstance(value, dict) else {}


def _team(game: dict[str, Any], side: str) -> tuple[int, str]:
    value = _teams(game).get(side)
    if not isinstance(value, dict):
        raise EvidenceError(f"{side}_team must be an object")
    return (
        _positive_int(value.get("id"), f"{side}_team_id"),
        _text(value.get("name"), f"{side}_team_name"),
    )


def _league_name(game: dict[str, Any]) -> str:
    value = game.get("league") or _nested_game(game).get("league")
    if isinstance(value, dict):
        value = value.get("name")
    return _text(value, "league")


def _provider_status(game: dict[str, Any]) -> str:
    value = _game_value(game, "status")
    if isinstance(value, dict):
        value = value.get("short") or value.get("long")
    return str(value or "UNKNOWN").strip() or "UNKNOWN"


@dataclass(frozen=True, slots=True)
class FixtureObservation:
    fixture_observation_id: str
    game_id: str
    provider: str
    provider_game_id: int
    league: str
    home_team_id: int
    home_team_name: str
    away_team_id: int
    away_team_name: str
    kickoff_at: str
    provider_status: str
    observed_at: str
    source_payload_ref: str
    source_payload_checksum: str
    schema_version: str

    def __post_init__(self) -> None:
        for name in (
            "fixture_observation_id",
            "game_id",
            "provider",
            "league",
            "home_team_name",
            "away_team_name",
            "provider_status",
            "source_payload_ref",
            "source_payload_checksum",
            "schema_version",
        ):
            _text(getattr(self, name), name)
        if self.provider != _PROVIDER:
            raise EvidenceError("provider is unsupported")
        provider_game_id = _positive_int(self.provider_game_id, "provider_game_id")
        home_team_id = _positive_int(self.home_team_id, "home_team_id")
        away_team_id = _positive_int(self.away_team_id, "away_team_id")
        if home_team_id == away_team_id:
            raise EvidenceError("home and away teams must differ")
        if self.game_id != str(provider_game_id):
            raise EvidenceError("game_id must match provider_game_id")
        _timestamp(self.kickoff_at, "kickoff_at")
        _timestamp(self.observed_at, "observed_at")
        checksum = self.source_payload_checksum
        if len(checksum) != 64 or any(
            char not in "0123456789abcdefABCDEF" for char in checksum
        ):
            raise EvidenceError(
                "source_payload_checksum must be a SHA-256 hex digest"
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def canonical_fixture_json(record: FixtureObservation) -> str:
    return json.dumps(
        record.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def canonical_fixture_observation(
    game: dict[str, Any],
    receipt: ArchiveReceipt,
) -> FixtureObservation | None:
    """Map one provider game row to immutable fixture evidence.

    Invalid or incomplete provider rows fail closed and return None.
    """

    try:
        provider_game_id = _positive_int(
            _game_value(game, "id"), "provider_game_id"
        )
        kickoff_raw = _game_value(game, "date")
        if isinstance(kickoff_raw, dict):
            kickoff_raw = kickoff_raw.get("date")
        kickoff_at = _text(kickoff_raw, "kickoff_at")
        _timestamp(kickoff_at, "kickoff_at")
        _timestamp(receipt.captured_at, "observed_at")
        home_team_id, home_team_name = _team(game, "home")
        away_team_id, away_team_name = _team(game, "away")
        league = _league_name(game)
        status = _provider_status(game)
    except EvidenceError:
        return None

    identity = {
        "game_id": str(provider_game_id),
        "provider": _PROVIDER,
        "provider_game_id": provider_game_id,
        "league": league,
        "home_team_id": home_team_id,
        "home_team_name": home_team_name,
        "away_team_id": away_team_id,
        "away_team_name": away_team_name,
        "kickoff_at": kickoff_at,
        "provider_status": status,
        "observed_at": receipt.captured_at,
        "source_payload_checksum": receipt.checksum,
    }
    canonical = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    observation_id = str(uuid.uuid5(_FIXTURE_NAMESPACE, canonical))

    try:
        return FixtureObservation(
            fixture_observation_id=observation_id,
            game_id=str(provider_game_id),
            provider=_PROVIDER,
            provider_game_id=provider_game_id,
            league=league,
            home_team_id=home_team_id,
            home_team_name=home_team_name,
            away_team_id=away_team_id,
            away_team_name=away_team_name,
            kickoff_at=kickoff_at,
            provider_status=status,
            observed_at=receipt.captured_at,
            source_payload_ref=receipt.ref,
            source_payload_checksum=receipt.checksum,
            schema_version="1.0",
        )
    except EvidenceError:
        return None
