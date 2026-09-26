"""Canonical slow-moving API-Sports Baseball evidence.

API-Sports is the primary provider for team strength, standings, schedules,
results and market reference data. This module keeps source facts compact and
derives algebraic features locally instead of spending more provider requests.
"""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from .evidence import EvidenceError
from .raw_archive import ArchiveReceipt

_PROVIDER = "api-sports-baseball"
_STANDING_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/api-sports-standing/v1",
)
_TEAM_STATS_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/api-sports-team-statistics/v1",
)
_CATALOG_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/api-sports-reference-catalog/v1",
)


def _timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{field} must be timezone-aware")
    return parsed


def _text(value: Any, field: str, *, required: bool = True) -> str | None:
    result = str(value or "").strip()
    if result:
        return result
    if required:
        raise EvidenceError(f"{field} must be non-empty")
    return None


def _integer(
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
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field} must be an integer") from exc
    if result < minimum:
        raise EvidenceError(f"{field} must be >= {minimum}")
    return result


def _number(
    value: Any,
    field: str,
    *,
    required: bool = True,
) -> float | None:
    if value in (None, ""):
        if required:
            raise EvidenceError(f"{field} is required")
        return None
    if isinstance(value, bool):
        raise EvidenceError(f"{field} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field} must be numeric") from exc
    if not math.isfinite(result):
        raise EvidenceError(f"{field} must be finite")
    return result


def _nested(value: Any, *path: str) -> Any:
    current = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _checksum(value: str) -> str:
    result = str(value or "").strip()
    if len(result) != 64 or any(
        char not in "0123456789abcdefABCDEF" for char in result
    ):
        raise EvidenceError("source_payload_checksum must be SHA-256")
    return result


def _uuid(namespace: uuid.UUID, identity: dict[str, Any]) -> str:
    canonical = json.dumps(
        identity,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return str(uuid.uuid5(namespace, canonical))


@dataclass(frozen=True, slots=True)
class StandingSnapshot:
    snapshot_id: str
    provider: str
    league_id: int
    season: int
    team_id: int
    team_name: str
    observed_at: str
    games_played: int
    wins: int
    losses: int
    win_percentage: float
    loss_percentage: float
    runs_for: float
    runs_against: float
    position: int | None
    stage: str | None
    group_name: str | None
    source_payload_ref: str
    source_payload_checksum: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.provider != _PROVIDER:
            raise EvidenceError("standing provider is unsupported")
        for field in (
            "snapshot_id",
            "team_name",
            "source_payload_ref",
            "schema_version",
        ):
            _text(getattr(self, field), field)
        _integer(self.league_id, "league_id", minimum=1)
        _integer(self.season, "season", minimum=1900)
        _integer(self.team_id, "team_id", minimum=1)
        _timestamp(self.observed_at, "observed_at")
        for field in ("games_played", "wins", "losses"):
            _integer(getattr(self, field), field, minimum=0)
        for field in (
            "win_percentage",
            "loss_percentage",
            "runs_for",
            "runs_against",
        ):
            _number(getattr(self, field), field)
        if self.position is not None:
            _integer(self.position, "position", minimum=1)
        _checksum(self.source_payload_checksum)

    @property
    def run_differential(self) -> float:
        return self.runs_for - self.runs_against

    @property
    def runs_per_game(self) -> float | None:
        if self.games_played == 0:
            return None
        return self.runs_for / self.games_played

    @property
    def runs_allowed_per_game(self) -> float | None:
        if self.games_played == 0:
            return None
        return self.runs_against / self.games_played

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TeamStatisticsSnapshot:
    snapshot_id: str
    provider: str
    league_id: int
    season: int
    team_id: int
    team_name: str
    observed_at: str
    games_played_all: int
    games_played_home: int
    games_played_away: int
    wins_all: int
    wins_home: int
    wins_away: int
    win_pct_all: float
    win_pct_home: float
    win_pct_away: float
    losses_all: int
    losses_home: int
    losses_away: int
    loss_pct_all: float
    loss_pct_home: float
    loss_pct_away: float
    runs_for_total_all: float
    runs_for_total_home: float
    runs_for_total_away: float
    runs_for_avg_all: float
    runs_for_avg_home: float
    runs_for_avg_away: float
    runs_against_total_all: float
    runs_against_total_home: float
    runs_against_total_away: float
    runs_against_avg_all: float
    runs_against_avg_home: float
    runs_against_avg_away: float
    source_payload_ref: str
    source_payload_checksum: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.provider != _PROVIDER:
            raise EvidenceError("team statistics provider is unsupported")
        for field in (
            "snapshot_id",
            "team_name",
            "source_payload_ref",
            "schema_version",
        ):
            _text(getattr(self, field), field)
        for field in ("league_id", "team_id"):
            _integer(getattr(self, field), field, minimum=1)
        _integer(self.season, "season", minimum=1900)
        _timestamp(self.observed_at, "observed_at")
        for field in (
            "games_played_all",
            "games_played_home",
            "games_played_away",
            "wins_all",
            "wins_home",
            "wins_away",
            "losses_all",
            "losses_home",
            "losses_away",
        ):
            _integer(getattr(self, field), field, minimum=0)
        for field in (
            "win_pct_all",
            "win_pct_home",
            "win_pct_away",
            "loss_pct_all",
            "loss_pct_home",
            "loss_pct_away",
            "runs_for_total_all",
            "runs_for_total_home",
            "runs_for_total_away",
            "runs_for_avg_all",
            "runs_for_avg_home",
            "runs_for_avg_away",
            "runs_against_total_all",
            "runs_against_total_home",
            "runs_against_total_away",
            "runs_against_avg_all",
            "runs_against_avg_home",
            "runs_against_avg_away",
        ):
            _number(getattr(self, field), field)
        _checksum(self.source_payload_checksum)

    def compact_features(self, *, side: str | None = None) -> dict[str, float | int]:
        """Return a non-redundant team-strength feature view.

        Counts remain provenance. Model code should prefer rates plus sample size
        instead of feeding wins, losses, win%, loss% and games as independent
        signals.
        """

        if side not in {None, "home", "away"}:
            raise EvidenceError("side must be home, away or None")
        suffix = "all" if side is None else side
        games = int(getattr(self, f"games_played_{suffix}"))
        win_pct = float(getattr(self, f"win_pct_{suffix}"))
        runs_for = float(getattr(self, f"runs_for_avg_{suffix}"))
        runs_against = float(getattr(self, f"runs_against_avg_{suffix}"))
        return {
            "sample_games": games,
            "win_pct": win_pct,
            "runs_per_game": runs_for,
            "runs_allowed_per_game": runs_against,
            "run_differential_per_game": runs_for - runs_against,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ReferenceCatalogSnapshot:
    snapshot_id: str
    provider: str
    catalog_type: str
    observed_at: str
    entries: tuple[tuple[int, str], ...]
    source_payload_ref: str
    source_payload_checksum: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.provider != _PROVIDER:
            raise EvidenceError("catalog provider is unsupported")
        if self.catalog_type not in {"BET_TYPES", "BOOKMAKERS"}:
            raise EvidenceError("catalog_type is unsupported")
        _timestamp(self.observed_at, "observed_at")
        if not self.entries:
            raise EvidenceError("catalog entries must be non-empty")
        ids: set[int] = set()
        for entry_id, name in self.entries:
            parsed = _integer(entry_id, "catalog entry id", minimum=1)
            assert parsed is not None
            _text(name, "catalog entry name")
            if parsed in ids:
                raise EvidenceError("catalog entries contain duplicate IDs")
            ids.add(parsed)
        _text(self.source_payload_ref, "source_payload_ref")
        _checksum(self.source_payload_checksum)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["entries"] = [
            {"id": entry_id, "name": name} for entry_id, name in self.entries
        ]
        return value


def canonical_standings(
    rows: list[dict[str, Any]],
    receipt: ArchiveReceipt,
    *,
    league_id: int,
    season: int,
) -> tuple[StandingSnapshot, ...]:
    observed_at = receipt.captured_at
    _timestamp(observed_at, "receipt.captured_at")
    result: list[StandingSnapshot] = []
    for row in rows:
        try:
            team_id = _integer(_nested(row, "team", "id"), "team.id", minimum=1)
            assert team_id is not None
            team_name = _text(_nested(row, "team", "name"), "team.name")
            assert team_name is not None
            games_played = _integer(
                _nested(row, "games", "played"),
                "games.played",
                minimum=0,
            )
            wins = _integer(
                _nested(row, "games", "win", "total"),
                "games.win.total",
                minimum=0,
            )
            losses = _integer(
                _nested(row, "games", "lose", "total"),
                "games.lose.total",
                minimum=0,
            )
            win_pct = _number(
                _nested(row, "games", "win", "percentage"),
                "games.win.percentage",
            )
            loss_pct = _number(
                _nested(row, "games", "lose", "percentage"),
                "games.lose.percentage",
            )
            runs_for = _number(_nested(row, "points", "for"), "points.for")
            runs_against = _number(
                _nested(row, "points", "against"),
                "points.against",
            )
            assert None not in (
                games_played,
                wins,
                losses,
                win_pct,
                loss_pct,
                runs_for,
                runs_against,
            )
            position = _integer(
                row.get("position"),
                "position",
                minimum=1,
                required=False,
            )
            stage = _text(row.get("stage"), "stage", required=False)
            group_name = _text(
                _nested(row, "group", "name"),
                "group.name",
                required=False,
            )
        except EvidenceError:
            continue

        identity = {
            "league_id": league_id,
            "season": season,
            "team_id": team_id,
            "observed_at": observed_at,
            "source_payload_checksum": receipt.checksum,
        }
        result.append(
            StandingSnapshot(
                snapshot_id=_uuid(_STANDING_NAMESPACE, identity),
                provider=_PROVIDER,
                league_id=league_id,
                season=season,
                team_id=team_id,
                team_name=team_name,
                observed_at=observed_at,
                games_played=int(games_played),
                wins=int(wins),
                losses=int(losses),
                win_percentage=float(win_pct),
                loss_percentage=float(loss_pct),
                runs_for=float(runs_for),
                runs_against=float(runs_against),
                position=int(position) if position is not None else None,
                stage=stage,
                group_name=group_name,
                source_payload_ref=receipt.ref,
                source_payload_checksum=receipt.checksum,
            )
        )
    return tuple(sorted(result, key=lambda item: item.team_id))


def canonical_team_statistics(
    payload: dict[str, Any],
    receipt: ArchiveReceipt,
) -> TeamStatisticsSnapshot:
    observed_at = receipt.captured_at
    _timestamp(observed_at, "receipt.captured_at")
    team_id = _integer(_nested(payload, "team", "id"), "team.id", minimum=1)
    league_id = _integer(_nested(payload, "league", "id"), "league.id", minimum=1)
    season = _integer(
        _nested(payload, "league", "season"), "league.season", minimum=1900
    )
    team_name = _text(_nested(payload, "team", "name"), "team.name")
    assert team_id is not None and league_id is not None and season is not None
    assert team_name is not None

    def integer(*path: str) -> int:
        value = _integer(_nested(payload, *path), ".".join(path), minimum=0)
        assert value is not None
        return value

    def number(*path: str) -> float:
        value = _number(_nested(payload, *path), ".".join(path))
        assert value is not None
        return value

    identity = {
        "league_id": league_id,
        "season": season,
        "team_id": team_id,
        "observed_at": observed_at,
        "source_payload_checksum": receipt.checksum,
    }
    return TeamStatisticsSnapshot(
        snapshot_id=_uuid(_TEAM_STATS_NAMESPACE, identity),
        provider=_PROVIDER,
        league_id=league_id,
        season=season,
        team_id=team_id,
        team_name=team_name,
        observed_at=observed_at,
        games_played_all=integer("games", "played", "all"),
        games_played_home=integer("games", "played", "home"),
        games_played_away=integer("games", "played", "away"),
        wins_all=integer("games", "wins", "all", "total"),
        wins_home=integer("games", "wins", "home", "total"),
        wins_away=integer("games", "wins", "away", "total"),
        win_pct_all=number("games", "wins", "all", "percentage"),
        win_pct_home=number("games", "wins", "home", "percentage"),
        win_pct_away=number("games", "wins", "away", "percentage"),
        losses_all=integer("games", "loses", "all", "total"),
        losses_home=integer("games", "loses", "home", "total"),
        losses_away=integer("games", "loses", "away", "total"),
        loss_pct_all=number("games", "loses", "all", "percentage"),
        loss_pct_home=number("games", "loses", "home", "percentage"),
        loss_pct_away=number("games", "loses", "away", "percentage"),
        runs_for_total_all=number("points", "for", "total", "all"),
        runs_for_total_home=number("points", "for", "total", "home"),
        runs_for_total_away=number("points", "for", "total", "away"),
        runs_for_avg_all=number("points", "for", "average", "all"),
        runs_for_avg_home=number("points", "for", "average", "home"),
        runs_for_avg_away=number("points", "for", "average", "away"),
        runs_against_total_all=number("points", "against", "total", "all"),
        runs_against_total_home=number("points", "against", "total", "home"),
        runs_against_total_away=number("points", "against", "total", "away"),
        runs_against_avg_all=number("points", "against", "average", "all"),
        runs_against_avg_home=number("points", "against", "average", "home"),
        runs_against_avg_away=number("points", "against", "average", "away"),
        source_payload_ref=receipt.ref,
        source_payload_checksum=receipt.checksum,
    )


def canonical_reference_catalog(
    rows: list[dict[str, Any]],
    receipt: ArchiveReceipt,
    *,
    catalog_type: str,
) -> ReferenceCatalogSnapshot:
    entries: list[tuple[int, str]] = []
    for row in rows:
        try:
            entry_id = _integer(row.get("id"), "catalog.id", minimum=1)
            name = _text(row.get("name"), "catalog.name")
            assert entry_id is not None and name is not None
        except EvidenceError:
            continue
        entries.append((entry_id, name))
    entries = sorted(set(entries), key=lambda item: item[0])
    identity = {
        "catalog_type": catalog_type,
        "observed_at": receipt.captured_at,
        "entries": entries,
        "source_payload_checksum": receipt.checksum,
    }
    return ReferenceCatalogSnapshot(
        snapshot_id=_uuid(_CATALOG_NAMESPACE, identity),
        provider=_PROVIDER,
        catalog_type=catalog_type,
        observed_at=receipt.captured_at,
        entries=tuple(entries),
        source_payload_ref=receipt.ref,
        source_payload_checksum=receipt.checksum,
    )


def canonical_json(
    record: StandingSnapshot | TeamStatisticsSnapshot | ReferenceCatalogSnapshot,
) -> str:
    return json.dumps(
        record.to_dict(),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
