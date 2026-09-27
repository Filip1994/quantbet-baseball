"""Bounded live Official MLB pregame enrichment.

This collector operates only on already-verified MLB game identity links. It
captures one immutable component set per game inside a configured pregame
window. Repeated cycles perform zero provider calls once a complete set exists.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from .evidence import EvidenceError
from .mlb_identity import MLBGameIdentityLink
from .official_mlb import OfficialMLBError, canonical_pregame_snapshot
from .official_mlb_components import (
    OfficialMLBPregameComponent,
    build_pregame_components,
)

_EXPECTED_COMPONENT_KEYS = {
    ("STARTER", "AWAY"),
    ("STARTER", "HOME"),
    ("LINEUP", "AWAY"),
    ("LINEUP", "HOME"),
    ("BULLPEN", "AWAY"),
    ("BULLPEN", "HOME"),
    ("VENUE", "GAME"),
}


class LiveEnrichmentClient(Protocol):
    def game_feed_with_receipt(
        self,
        game_pk: int,
        *,
        timecode: str | None = None,
        captured_at: datetime | None = None,
    ): ...


class LiveEnrichmentIdentityRepository(Protocol):
    def game_links(
        self,
        mapping_version: str,
    ) -> tuple[MLBGameIdentityLink, ...]: ...


class LiveEnrichmentComponentRepository(Protocol):
    def latest_components_for_game(
        self,
        *,
        mlb_game_pk: int,
        as_of: datetime,
    ) -> tuple[OfficialMLBPregameComponent, ...]: ...

    def append_components(
        self,
        records: tuple[OfficialMLBPregameComponent, ...],
    ) -> int: ...


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError("identity first pitch must be timezone-aware")
    return parsed.astimezone(UTC)


def _component_keys(
    rows: tuple[OfficialMLBPregameComponent, ...],
) -> set[tuple[str, str]]:
    return {(row.component_type, row.side) for row in rows}


def _is_complete_component_set(
    rows: tuple[OfficialMLBPregameComponent, ...],
) -> bool:
    return len(rows) == 7 and _component_keys(rows) == _EXPECTED_COMPONENT_KEYS


def collect_live_pregame_components(
    client: LiveEnrichmentClient,
    identity_repository: LiveEnrichmentIdentityRepository,
    component_repository: LiveEnrichmentComponentRepository,
    *,
    mapping_version: str,
    now: datetime,
    horizon_minutes: int = 150,
    max_calls: int = 4,
) -> dict[str, int | str]:
    """Capture one live PIT component set for each due linked game.

    V1 deliberately captures only once per game. State-aware lineup/final
    refreshes are a later stage and must not be inferred from this collector.
    """

    if horizon_minutes < 1:
        raise ValueError("horizon_minutes must be positive")
    if max_calls < 1:
        raise ValueError("max_calls must be positive")

    current = _utc(now)
    links = identity_repository.game_links(mapping_version)
    upcoming = tuple(
        sorted(
            (
                link
                for link in links
                if 0
                < (_timestamp(link.official_mlb_first_pitch) - current).total_seconds()
                <= horizon_minutes * 60
            ),
            key=lambda link: (
                _timestamp(link.official_mlb_first_pitch),
                link.api_sports_provider_game_id,
            ),
        )
    )

    result: dict[str, int | str] = {
        "status": "NO_DUE_GAMES",
        "mapping_version": mapping_version,
        "linked_games_total": len(links),
        "due_games": len(upcoming),
        "already_captured": 0,
        "partial_existing": 0,
        "provider_calls": 0,
        "games_completed": 0,
        "components_inserted": 0,
        "due_games_uncollected": 0,
        "failures": 0,
        "ready_for_feature_snapshot": 0,
    }
    if not upcoming:
        return result

    due: list[MLBGameIdentityLink] = []
    for link in upcoming:
        existing = component_repository.latest_components_for_game(
            mlb_game_pk=link.mlb_game_pk,
            as_of=current,
        )
        if _is_complete_component_set(existing):
            result["already_captured"] = int(result["already_captured"]) + 1
            continue
        if existing:
            result["partial_existing"] = int(result["partial_existing"]) + 1
            result["failures"] = int(result["failures"]) + 1
            continue
        due.append(link)

    for link in due[:max_calls]:
        first_pitch = _timestamp(link.official_mlb_first_pitch)
        try:
            payload, receipt = client.game_feed_with_receipt(link.mlb_game_pk)
            result["provider_calls"] = int(result["provider_calls"]) + 1
            snapshot = canonical_pregame_snapshot(payload, receipt)
            retrieved_at = _timestamp(snapshot.retrieved_at)
            if retrieved_at >= first_pitch:
                raise EvidenceError(
                    "live Official MLB evidence was retrieved at or after first pitch"
                )
        except (OfficialMLBError, EvidenceError, ValueError):
            result["failures"] = int(result["failures"]) + 1
            continue

        if (
            snapshot.mlb_game_pk != link.mlb_game_pk
            or snapshot.home_team_id != link.mlb_home_team_id
            or snapshot.away_team_id != link.mlb_away_team_id
        ):
            result["failures"] = int(result["failures"]) + 1
            continue

        rows = build_pregame_components(payload, receipt)
        if not _is_complete_component_set(rows):
            result["failures"] = int(result["failures"]) + 1
            continue

        inserted = component_repository.append_components(rows)
        readback = component_repository.latest_components_for_game(
            mlb_game_pk=link.mlb_game_pk,
            as_of=retrieved_at,
        )
        eligible = _is_complete_component_set(readback) and all(
            _timestamp(row.source_observed_at) < first_pitch for row in readback
        )
        if not eligible:
            result["failures"] = int(result["failures"]) + 1
            continue

        result["games_completed"] = int(result["games_completed"]) + 1
        result["components_inserted"] = int(result["components_inserted"]) + inserted

    uncollected = max(0, len(due) - max_calls)
    result["due_games_uncollected"] = uncollected
    complete_games = int(result["already_captured"]) + int(result["games_completed"])
    result["ready_for_feature_snapshot"] = complete_games

    if int(result["failures"]) > 0:
        result["status"] = "PARTIAL"
    elif uncollected > 0:
        result["status"] = "CAPACITY_LIMITED"
    else:
        result["status"] = "COMPLETE"
    return result
