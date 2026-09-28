"""Explicit league registry for production-safe multi-league baseball paths."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BaseballLeague:
    code: str
    league_id: int
    names: tuple[str, ...]


CORE_LEAGUES: tuple[BaseballLeague, ...] = (
    BaseballLeague("MLB", 1, ("MLB", "Major League Baseball")),
    BaseballLeague("NPB", 2, ("NPB", "Nippon Professional Baseball")),
    BaseballLeague("LIDOM", 11, ("LIDOM",)),
    BaseballLeague("LMB", 21, ("LMB", "Liga Mexicana de Beisbol", "Liga Mexicana de Béisbol")),
)

_BY_ID = {league.league_id: league for league in CORE_LEAGUES}
_BY_NAME = {
    name.strip().casefold(): league
    for league in CORE_LEAGUES
    for name in league.names
}


def league_for_id(league_id: int) -> BaseballLeague:
    try:
        return _BY_ID[int(league_id)]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"unsupported baseball league id: {league_id}") from exc


def league_for_name(name: str) -> BaseballLeague:
    key = str(name or "").strip().casefold()
    if not key:
        raise ValueError("league name must be non-empty")
    try:
        return _BY_NAME[key]
    except KeyError as exc:
        raise ValueError(f"unsupported baseball league: {name}") from exc


def parse_league_ids(value: str, *, default: tuple[int, ...] = (1,)) -> tuple[int, ...]:
    raw = str(value or "").strip()
    if not raw:
        return default
    result: list[int] = []
    for token in raw.split(","):
        league = league_for_id(int(token.strip()))
        if league.league_id not in result:
            result.append(league.league_id)
    return tuple(result)


def league_names_for_ids(league_ids: tuple[int, ...]) -> tuple[str, ...]:
    names: list[str] = []
    for league_id in league_ids:
        names.extend(league_for_id(league_id).names)
    return tuple(names)
