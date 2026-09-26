"""API-Sports game-history evidence and point-in-time schedule derivations.

API-Sports remains canonical for schedule, history, game status and results.
Raw provider envelopes are archived before these compact snapshots are built.

Historical replay rule:
- a source snapshot is eligible only when observed_at <= decision cutoff;
- completed-game facts may only influence a later target game;
- current target-game scores are never exposed as pregame features.
"""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from .evidence import EvidenceError
from .raw_archive import ArchiveReceipt

_PROVIDER = "api-sports-baseball"
_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/api-sports-game-history/v1",
)


def _timestamp(value: Any, field: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise EvidenceError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise EvidenceError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def _text(value: Any, field: str, *, required: bool = True) -> str | None:
    result = str(value or "").strip()
    if result:
        return result
    if required:
        raise EvidenceError(f"{field} must be non-empty")
    return None


def _int(
    value: Any,
    field: str,
    *,
    minimum: int = 0,
    required: bool = True,
) -> int | None:
    if value in (None, ""):
        if required:
            raise EvidenceError(f"{field} is required")
        return None
    if isinstance(value, bool):
        raise EvidenceError(f"{field} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field} must be an integer") from exc
    if number < minimum:
        raise EvidenceError(f"{field} must be >= {minimum}")
    return number


def _nested(value: Any, *path: str) -> Any:
    current = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _checksum(value: str) -> str:
    checksum = str(value or "").strip()
    if len(checksum) != 64 or any(
        char not in "0123456789abcdefABCDEF" for char in checksum
    ):
        raise EvidenceError("source_payload_checksum must be SHA-256")
    return checksum


def _innings(value: Any) -> dict[str, int | None]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int | None] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key).strip()
        if not key:
            continue
        if raw_value is None:
            result[key] = None
            continue
        parsed = _int(raw_value, f"innings.{key}", minimum=0)
        assert parsed is not None
        result[key] = parsed
    return result


@dataclass(frozen=True, slots=True)
class GameHistorySnapshot:
    snapshot_id: str
    provider: str
    provider_game_id: int
    observed_at: str
    scheduled_first_pitch: str
    provider_timezone: str
    status_long: str
    status_short: str
    league_id: int
    season: int
    home_team_id: int
    home_team_name: str
    away_team_id: int
    away_team_name: str
    home_score: int | None
    away_score: int | None
    home_hits: int | None
    away_hits: int | None
    home_errors: int | None
    away_errors: int | None
    home_innings: dict[str, int | None]
    away_innings: dict[str, int | None]
    source_payload_ref: str
    source_payload_checksum: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.provider != _PROVIDER:
            raise EvidenceError("game-history provider is unsupported")
        for field in (
            "snapshot_id",
            "provider_timezone",
            "status_long",
            "status_short",
            "home_team_name",
            "away_team_name",
            "source_payload_ref",
            "schema_version",
        ):
            _text(getattr(self, field), field)
        _int(self.provider_game_id, "provider_game_id", minimum=1)
        _int(self.league_id, "league_id", minimum=1)
        _int(self.season, "season", minimum=1900)
        _int(self.home_team_id, "home_team_id", minimum=1)
        _int(self.away_team_id, "away_team_id", minimum=1)
        if self.home_team_id == self.away_team_id:
            raise EvidenceError("home and away teams must differ")
        _timestamp(self.observed_at, "observed_at")
        _timestamp(self.scheduled_first_pitch, "scheduled_first_pitch")
        for field in (
            "home_score",
            "away_score",
            "home_hits",
            "away_hits",
            "home_errors",
            "away_errors",
        ):
            value = getattr(self, field)
            if value is not None:
                _int(value, field, minimum=0)
        _checksum(self.source_payload_checksum)

    @property
    def is_final(self) -> bool:
        return self.status_short.upper() == "FT"

    @property
    def went_extra_innings(self) -> bool | None:
        if not self.is_final:
            return None
        home_extra = self.home_innings.get("extra")
        away_extra = self.away_innings.get("extra")
        if home_extra is None and away_extra is None:
            return False
        return True

    @property
    def total_runs(self) -> int | None:
        if self.home_score is None or self.away_score is None:
            return None
        return self.home_score + self.away_score

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TeamScheduleFeatures:
    team_id: int
    target_game_id: int
    source_cutoff_at: str
    previous_game_id: int | None
    previous_game_first_pitch: str | None
    hours_since_previous_first_pitch: float | None
    utc_calendar_days_off: int | None
    games_last_72h: int
    games_last_168h: int
    previous_game_went_extra_innings: bool | None
    current_site: str
    current_site_streak_games: int
    same_opponent_consecutive_games: int
    same_utc_day_games: int
    inferred_doubleheader: bool
    source_games_considered: int
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        _int(self.team_id, "team_id", minimum=1)
        _int(self.target_game_id, "target_game_id", minimum=1)
        _timestamp(self.source_cutoff_at, "source_cutoff_at")
        if self.current_site not in {"HOME", "AWAY"}:
            raise EvidenceError("current_site is unsupported")
        for field in (
            "games_last_72h",
            "games_last_168h",
            "current_site_streak_games",
            "same_opponent_consecutive_games",
            "same_utc_day_games",
            "source_games_considered",
        ):
            _int(getattr(self, field), field, minimum=0)
        if self.hours_since_previous_first_pitch is not None:
            value = float(self.hours_since_previous_first_pitch)
            if not math.isfinite(value) or value < 0:
                raise EvidenceError(
                    "hours_since_previous_first_pitch must be finite/non-negative"
                )
        if self.utc_calendar_days_off is not None:
            _int(self.utc_calendar_days_off, "utc_calendar_days_off", minimum=0)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def canonical_game_history(
    rows: list[dict[str, Any]],
    receipt: ArchiveReceipt,
    *,
    league_id: int | None = None,
    season: int | None = None,
) -> tuple[GameHistorySnapshot, ...]:
    """Canonicalize archived API-Sports game rows without fabricating null fields."""

    observed_at = receipt.captured_at
    _timestamp(observed_at, "receipt.captured_at")
    result: list[GameHistorySnapshot] = []

    for row in rows:
        try:
            provider_game_id = _int(row.get("id"), "id", minimum=1)
            row_league_id = _int(_nested(row, "league", "id"), "league.id", minimum=1)
            row_season = _int(
                _nested(row, "league", "season"),
                "league.season",
                minimum=1900,
            )
            assert provider_game_id is not None
            assert row_league_id is not None
            assert row_season is not None
            if league_id is not None and row_league_id != league_id:
                continue
            if season is not None and row_season != season:
                continue

            scheduled = _timestamp(row.get("date"), "date").isoformat()
            timezone = _text(row.get("timezone"), "timezone")
            status_long = _text(_nested(row, "status", "long"), "status.long")
            status_short = _text(_nested(row, "status", "short"), "status.short")
            home_team_id = _int(
                _nested(row, "teams", "home", "id"),
                "teams.home.id",
                minimum=1,
            )
            away_team_id = _int(
                _nested(row, "teams", "away", "id"),
                "teams.away.id",
                minimum=1,
            )
            home_name = _text(
                _nested(row, "teams", "home", "name"),
                "teams.home.name",
            )
            away_name = _text(
                _nested(row, "teams", "away", "name"),
                "teams.away.name",
            )
            assert timezone is not None
            assert status_long is not None
            assert status_short is not None
            assert home_team_id is not None
            assert away_team_id is not None
            assert home_name is not None
            assert away_name is not None
        except EvidenceError:
            continue

        def optional_score(*path: str) -> int | None:
            return _int(
                _nested(row, *path),
                ".".join(path),
                minimum=0,
                required=False,
            )

        identity = {
            "provider_game_id": provider_game_id,
            "observed_at": observed_at,
            "source_payload_checksum": receipt.checksum,
        }
        snapshot_id = str(
            uuid.uuid5(
                _NAMESPACE,
                json.dumps(identity, sort_keys=True, separators=(",", ":")),
            )
        )

        result.append(
            GameHistorySnapshot(
                snapshot_id=snapshot_id,
                provider=_PROVIDER,
                provider_game_id=provider_game_id,
                observed_at=observed_at,
                scheduled_first_pitch=scheduled,
                provider_timezone=timezone,
                status_long=status_long,
                status_short=status_short,
                league_id=row_league_id,
                season=row_season,
                home_team_id=home_team_id,
                home_team_name=home_name,
                away_team_id=away_team_id,
                away_team_name=away_name,
                home_score=optional_score("scores", "home", "total"),
                away_score=optional_score("scores", "away", "total"),
                home_hits=optional_score("scores", "home", "hits"),
                away_hits=optional_score("scores", "away", "hits"),
                home_errors=optional_score("scores", "home", "errors"),
                away_errors=optional_score("scores", "away", "errors"),
                home_innings=_innings(_nested(row, "scores", "home", "innings")),
                away_innings=_innings(_nested(row, "scores", "away", "innings")),
                source_payload_ref=receipt.ref,
                source_payload_checksum=_checksum(receipt.checksum),
            )
        )

    return tuple(
        sorted(
            result, key=lambda item: (item.scheduled_first_pitch, item.provider_game_id)
        )
    )


def _team_site(game: GameHistorySnapshot, team_id: int) -> str | None:
    if game.home_team_id == team_id:
        return "HOME"
    if game.away_team_id == team_id:
        return "AWAY"
    return None


def _opponent_id(game: GameHistorySnapshot, team_id: int) -> int | None:
    if game.home_team_id == team_id:
        return game.away_team_id
    if game.away_team_id == team_id:
        return game.home_team_id
    return None


def derive_team_schedule_features(
    *,
    target: GameHistorySnapshot,
    team_id: int,
    history: tuple[GameHistorySnapshot, ...] | list[GameHistorySnapshot],
    cutoff_at: str,
) -> TeamScheduleFeatures:
    """Derive schedule context only from snapshots known by the decision cutoff."""

    cutoff = _timestamp(cutoff_at, "cutoff_at")
    target_start = _timestamp(
        target.scheduled_first_pitch, "target.scheduled_first_pitch"
    )
    target_observed = _timestamp(target.observed_at, "target.observed_at")
    if target_observed > cutoff:
        raise EvidenceError("target schedule snapshot exceeds decision cutoff")
    if cutoff >= target_start:
        raise EvidenceError("schedule feature cutoff must precede target first pitch")

    site = _team_site(target, team_id)
    if site is None:
        raise EvidenceError("team_id is not part of target game")
    opponent = _opponent_id(target, team_id)
    assert opponent is not None

    latest_by_game: dict[int, GameHistorySnapshot] = {}
    for game in history:
        if game.provider_game_id == target.provider_game_id:
            continue
        if game.league_id != target.league_id or game.season != target.season:
            continue
        if _team_site(game, team_id) is None:
            continue
        observed = _timestamp(game.observed_at, "game.observed_at")
        if observed > cutoff:
            continue
        existing = latest_by_game.get(game.provider_game_id)
        if existing is None or observed > _timestamp(
            existing.observed_at,
            "existing.observed_at",
        ):
            latest_by_game[game.provider_game_id] = game

    eligible = list(latest_by_game.values())

    prior_played = [
        game
        for game in eligible
        if game.is_final
        and _timestamp(game.scheduled_first_pitch, "game.scheduled_first_pitch")
        < target_start
    ]
    prior_played.sort(
        key=lambda game: (
            _timestamp(game.scheduled_first_pitch, "game.scheduled_first_pitch"),
            game.provider_game_id,
        )
    )

    previous = prior_played[-1] if prior_played else None
    hours_since_previous: float | None = None
    utc_days_off: int | None = None
    previous_extra: bool | None = None
    if previous is not None:
        previous_start = _timestamp(
            previous.scheduled_first_pitch,
            "previous.scheduled_first_pitch",
        )
        hours_since_previous = (target_start - previous_start).total_seconds() / 3600
        utc_days_off = max(0, (target_start.date() - previous_start.date()).days - 1)
        previous_extra = previous.went_extra_innings

    def count_window(hours: int) -> int:
        lower = target_start.timestamp() - hours * 3600
        return sum(
            1
            for game in prior_played
            if _timestamp(
                game.scheduled_first_pitch,
                "game.scheduled_first_pitch",
            ).timestamp()
            >= lower
        )

    site_streak = 1
    for game in reversed(prior_played):
        if _team_site(game, team_id) != site:
            break
        site_streak += 1

    matchup_streak = 1
    for game in reversed(prior_played):
        if _opponent_id(game, team_id) != opponent:
            break
        matchup_streak += 1

    same_utc_date = target_start.date()
    same_day_games = 1
    for game in eligible:
        game_start = _timestamp(
            game.scheduled_first_pitch,
            "game.scheduled_first_pitch",
        )
        if game_start.date() == same_utc_date:
            same_day_games += 1

    return TeamScheduleFeatures(
        team_id=team_id,
        target_game_id=target.provider_game_id,
        source_cutoff_at=cutoff.isoformat(),
        previous_game_id=previous.provider_game_id if previous else None,
        previous_game_first_pitch=(
            previous.scheduled_first_pitch if previous else None
        ),
        hours_since_previous_first_pitch=hours_since_previous,
        utc_calendar_days_off=utc_days_off,
        games_last_72h=count_window(72),
        games_last_168h=count_window(168),
        previous_game_went_extra_innings=previous_extra,
        current_site=site,
        current_site_streak_games=site_streak,
        same_opponent_consecutive_games=matchup_streak,
        same_utc_day_games=same_day_games,
        inferred_doubleheader=same_day_games >= 2,
        source_games_considered=len(eligible),
    )


def canonical_game_history_json(record: GameHistorySnapshot) -> str:
    return json.dumps(
        record.to_dict(),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
