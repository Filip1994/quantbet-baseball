"""Fail-close API-Sports fixture to official MLB game identity bridge."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable

from .evidence import EvidenceError
from .fixture_evidence import FixtureObservation
from .raw_archive import ArchiveReceipt

_TEAM_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/official-mlb-team-identity/v1",
)
_GAME_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/official-mlb-game-identity/v1",
)


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise EvidenceError(f"{field} must be a positive integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field} must be a positive integer") from exc
    if number <= 0:
        raise EvidenceError(f"{field} must be a positive integer")
    return number


def _text(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise EvidenceError(f"{field} must be non-empty")
    return result


def _timestamp(value: Any, field: str) -> datetime:
    raw = _text(value, field).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise EvidenceError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def _checksum(value: Any, field: str) -> str:
    raw = _text(value, field)
    if len(raw) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in raw):
        raise EvidenceError(f"{field} must be a SHA-256 hex digest")
    return raw.lower()


def _normalized_name(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _canonical_json(value: Any) -> str:
    payload = value.to_dict() if hasattr(value, "to_dict") else value
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


@dataclass(frozen=True, slots=True)
class MLBTeamIdentityMapping:
    mapping_id: str
    mapping_version: str
    api_sports_team_id: int
    api_sports_team_name: str
    official_mlb_team_id: int
    official_mlb_team_name: str
    verified_at: str
    api_fixture_observation_id: str
    api_source_payload_ref: str
    api_source_payload_checksum: str
    mlb_schedule_source_payload_ref: str
    mlb_schedule_source_payload_checksum: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field in (
            "mapping_id",
            "mapping_version",
            "api_sports_team_name",
            "official_mlb_team_name",
            "api_fixture_observation_id",
            "api_source_payload_ref",
            "mlb_schedule_source_payload_ref",
            "schema_version",
        ):
            _text(getattr(self, field), field)
        _positive_int(self.api_sports_team_id, "api_sports_team_id")
        _positive_int(self.official_mlb_team_id, "official_mlb_team_id")
        _timestamp(self.verified_at, "verified_at")
        _checksum(self.api_source_payload_checksum, "api_source_payload_checksum")
        _checksum(
            self.mlb_schedule_source_payload_checksum,
            "mlb_schedule_source_payload_checksum",
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MLBGameIdentityLink:
    link_id: str
    mapping_version: str
    game_id: str
    api_sports_provider_game_id: int
    mlb_game_pk: int
    api_home_team_id: int
    api_away_team_id: int
    mlb_home_team_id: int
    mlb_away_team_id: int
    api_sports_first_pitch: str
    official_mlb_first_pitch: str
    kickoff_delta_seconds: int
    linked_at: str
    api_fixture_observation_id: str
    api_source_payload_ref: str
    api_source_payload_checksum: str
    mlb_schedule_source_payload_ref: str
    mlb_schedule_source_payload_checksum: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field in (
            "link_id",
            "mapping_version",
            "game_id",
            "api_fixture_observation_id",
            "api_source_payload_ref",
            "mlb_schedule_source_payload_ref",
            "schema_version",
        ):
            _text(getattr(self, field), field)
        provider_game_id = _positive_int(
            self.api_sports_provider_game_id,
            "api_sports_provider_game_id",
        )
        if self.game_id != str(provider_game_id):
            raise EvidenceError("game_id must equal API-Sports provider game id")
        _positive_int(self.mlb_game_pk, "mlb_game_pk")
        _positive_int(self.api_home_team_id, "api_home_team_id")
        _positive_int(self.api_away_team_id, "api_away_team_id")
        _positive_int(self.mlb_home_team_id, "mlb_home_team_id")
        _positive_int(self.mlb_away_team_id, "mlb_away_team_id")
        _timestamp(self.api_sports_first_pitch, "api_sports_first_pitch")
        _timestamp(self.official_mlb_first_pitch, "official_mlb_first_pitch")
        _timestamp(self.linked_at, "linked_at")
        if self.kickoff_delta_seconds < 0:
            raise EvidenceError("kickoff_delta_seconds cannot be negative")
        _checksum(self.api_source_payload_checksum, "api_source_payload_checksum")
        _checksum(
            self.mlb_schedule_source_payload_checksum,
            "mlb_schedule_source_payload_checksum",
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MLBTeamIdentityRegistry:
    """Versioned, one-to-one API-Sports -> official MLB team identity registry."""

    def __init__(self, mappings: Iterable[MLBTeamIdentityMapping]) -> None:
        rows = tuple(mappings)
        if not rows:
            raise EvidenceError("MLB team identity registry cannot be empty")
        versions = {row.mapping_version for row in rows}
        if len(versions) != 1:
            raise EvidenceError("MLB team identity registry must use one version")
        by_api: dict[int, MLBTeamIdentityMapping] = {}
        by_mlb: dict[int, MLBTeamIdentityMapping] = {}
        for row in rows:
            if row.api_sports_team_id in by_api:
                raise EvidenceError("duplicate API-Sports team identity")
            if row.official_mlb_team_id in by_mlb:
                raise EvidenceError("duplicate official MLB team identity")
            by_api[row.api_sports_team_id] = row
            by_mlb[row.official_mlb_team_id] = row
        self.mapping_version = rows[0].mapping_version
        self._by_api = by_api

    def require_api_team(self, team_id: int) -> MLBTeamIdentityMapping:
        row = self._by_api.get(_positive_int(team_id, "api_sports_team_id"))
        if row is None:
            raise EvidenceError("API-Sports team is absent from MLB identity registry")
        return row


@dataclass(frozen=True, slots=True)
class _ScheduleGame:
    game_pk: int
    first_pitch: datetime
    home_team_id: int
    home_team_name: str
    away_team_id: int
    away_team_name: str


def _schedule_games(payload: dict[str, Any]) -> tuple[_ScheduleGame, ...]:
    dates = payload.get("dates")
    if not isinstance(dates, list):
        raise EvidenceError("official MLB schedule dates must be a list")
    result: list[_ScheduleGame] = []
    for date_row in dates:
        if not isinstance(date_row, dict):
            continue
        games = date_row.get("games")
        if not isinstance(games, list):
            continue
        for game in games:
            if not isinstance(game, dict):
                continue
            teams = game.get("teams")
            if not isinstance(teams, dict):
                continue
            home = teams.get("home")
            away = teams.get("away")
            if not isinstance(home, dict) or not isinstance(away, dict):
                continue
            home_team = home.get("team")
            away_team = away.get("team")
            if not isinstance(home_team, dict) or not isinstance(away_team, dict):
                continue
            try:
                result.append(
                    _ScheduleGame(
                        game_pk=_positive_int(game.get("gamePk"), "gamePk"),
                        first_pitch=_timestamp(game.get("gameDate"), "gameDate"),
                        home_team_id=_positive_int(
                            home_team.get("id"),
                            "schedule.home.team.id",
                        ),
                        home_team_name=_text(
                            home_team.get("name"),
                            "schedule.home.team.name",
                        ),
                        away_team_id=_positive_int(
                            away_team.get("id"),
                            "schedule.away.team.id",
                        ),
                        away_team_name=_text(
                            away_team.get("name"),
                            "schedule.away.team.name",
                        ),
                    )
                )
            except EvidenceError:
                continue
    return tuple(result)


def _fixture_is_mlb(fixture: FixtureObservation) -> None:
    if fixture.league.strip().casefold() != "mlb":
        raise EvidenceError("official MLB identity bridge accepts MLB fixtures only")


def _within_tolerance(
    fixture: FixtureObservation,
    game: _ScheduleGame,
    tolerance: timedelta,
) -> bool:
    if tolerance.total_seconds() < 0:
        raise EvidenceError("kickoff tolerance cannot be negative")
    fixture_pitch = _timestamp(fixture.kickoff_at, "fixture.kickoff_at")
    return (
        abs((game.first_pitch - fixture_pitch).total_seconds())
        <= tolerance.total_seconds()
    )


def propose_team_identity_mappings(
    fixture: FixtureObservation,
    schedule_payload: dict[str, Any],
    schedule_receipt: ArchiveReceipt,
    *,
    mapping_version: str,
    verified_at: datetime | None = None,
    kickoff_tolerance: timedelta = timedelta(minutes=30),
) -> tuple[MLBTeamIdentityMapping, MLBTeamIdentityMapping]:
    """Bootstrap two team mappings from an exact-name, same-game identity proof.

    This helper is for controlled registry construction. Production game linking
    must use a pre-existing versioned registry and therefore does not depend on
    team-name matching at prediction time.
    """

    _fixture_is_mlb(fixture)
    version = _text(mapping_version, "mapping_version")
    candidates = [
        game
        for game in _schedule_games(schedule_payload)
        if _normalized_name(game.home_team_name)
        == _normalized_name(fixture.home_team_name)
        and _normalized_name(game.away_team_name)
        == _normalized_name(fixture.away_team_name)
        and _within_tolerance(fixture, game, kickoff_tolerance)
    ]
    if len(candidates) != 1:
        raise EvidenceError(
            "team identity bootstrap requires exactly one exact-name/time match"
        )
    game = candidates[0]
    when = (
        verified_at or _timestamp(schedule_receipt.captured_at, "captured_at")
    ).astimezone(UTC)

    def build(
        api_team_id: int,
        api_team_name: str,
        mlb_team_id: int,
        mlb_team_name: str,
    ) -> MLBTeamIdentityMapping:
        identity = {
            "mapping_version": version,
            "api_sports_team_id": api_team_id,
            "official_mlb_team_id": mlb_team_id,
        }
        mapping_id = str(
            uuid.uuid5(
                _TEAM_NAMESPACE,
                json.dumps(identity, sort_keys=True, separators=(",", ":")),
            )
        )
        return MLBTeamIdentityMapping(
            mapping_id=mapping_id,
            mapping_version=version,
            api_sports_team_id=api_team_id,
            api_sports_team_name=api_team_name,
            official_mlb_team_id=mlb_team_id,
            official_mlb_team_name=mlb_team_name,
            verified_at=when.isoformat(),
            api_fixture_observation_id=fixture.fixture_observation_id,
            api_source_payload_ref=fixture.source_payload_ref,
            api_source_payload_checksum=fixture.source_payload_checksum,
            mlb_schedule_source_payload_ref=schedule_receipt.ref,
            mlb_schedule_source_payload_checksum=schedule_receipt.checksum,
        )

    return (
        build(
            fixture.home_team_id,
            fixture.home_team_name,
            game.home_team_id,
            game.home_team_name,
        ),
        build(
            fixture.away_team_id,
            fixture.away_team_name,
            game.away_team_id,
            game.away_team_name,
        ),
    )


def link_fixture_to_mlb_game(
    fixture: FixtureObservation,
    schedule_payload: dict[str, Any],
    schedule_receipt: ArchiveReceipt,
    registry: MLBTeamIdentityRegistry,
    *,
    linked_at: datetime | None = None,
    kickoff_tolerance: timedelta = timedelta(minutes=30),
) -> MLBGameIdentityLink:
    """Resolve one API-Sports MLB fixture to one official MLB gamePk or fail closed."""

    _fixture_is_mlb(fixture)
    home = registry.require_api_team(fixture.home_team_id)
    away = registry.require_api_team(fixture.away_team_id)
    if _normalized_name(home.api_sports_team_name) != _normalized_name(
        fixture.home_team_name
    ):
        raise EvidenceError(
            "home API-Sports team name disagrees with identity registry"
        )
    if _normalized_name(away.api_sports_team_name) != _normalized_name(
        fixture.away_team_name
    ):
        raise EvidenceError(
            "away API-Sports team name disagrees with identity registry"
        )

    candidates = [
        game
        for game in _schedule_games(schedule_payload)
        if game.home_team_id == home.official_mlb_team_id
        and game.away_team_id == away.official_mlb_team_id
        and _normalized_name(game.home_team_name)
        == _normalized_name(home.official_mlb_team_name)
        and _normalized_name(game.away_team_name)
        == _normalized_name(away.official_mlb_team_name)
        and _within_tolerance(fixture, game, kickoff_tolerance)
    ]
    if len(candidates) != 1:
        raise EvidenceError("MLB game identity requires exactly one ID/time match")
    game = candidates[0]
    api_pitch = _timestamp(fixture.kickoff_at, "fixture.kickoff_at")
    delta_seconds = int(abs((game.first_pitch - api_pitch).total_seconds()))
    linked = (
        linked_at or _timestamp(schedule_receipt.captured_at, "captured_at")
    ).astimezone(UTC)
    identity = {
        "mapping_version": registry.mapping_version,
        "api_sports_provider_game_id": fixture.provider_game_id,
        "mlb_game_pk": game.game_pk,
    }
    link_id = str(
        uuid.uuid5(
            _GAME_NAMESPACE,
            json.dumps(identity, sort_keys=True, separators=(",", ":")),
        )
    )
    return MLBGameIdentityLink(
        link_id=link_id,
        mapping_version=registry.mapping_version,
        game_id=fixture.game_id,
        api_sports_provider_game_id=fixture.provider_game_id,
        mlb_game_pk=game.game_pk,
        api_home_team_id=fixture.home_team_id,
        api_away_team_id=fixture.away_team_id,
        mlb_home_team_id=game.home_team_id,
        mlb_away_team_id=game.away_team_id,
        api_sports_first_pitch=api_pitch.isoformat(),
        official_mlb_first_pitch=game.first_pitch.isoformat(),
        kickoff_delta_seconds=delta_seconds,
        linked_at=linked.isoformat(),
        api_fixture_observation_id=fixture.fixture_observation_id,
        api_source_payload_ref=fixture.source_payload_ref,
        api_source_payload_checksum=fixture.source_payload_checksum,
        mlb_schedule_source_payload_ref=schedule_receipt.ref,
        mlb_schedule_source_payload_checksum=schedule_receipt.checksum,
    )


def canonical_team_identity_json(record: MLBTeamIdentityMapping) -> str:
    return _canonical_json(record)


def canonical_game_identity_json(record: MLBGameIdentityLink) -> str:
    return _canonical_json(record)
