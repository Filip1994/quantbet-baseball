"""Restart-safe materialization of Moneyline V1 feature snapshots."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from .evidence import EvidenceError
from .feature_snapshot import FeatureSnapshot
from .mlb_identity import MLBGameIdentityLink
from .moneyline_features import (
    FEATURE_VERSION,
    MLB_API_SPORTS_LEAGUE_ID,
    ComponentRepository,
    FixtureRepository,
    IdentityRepository,
    ProviderDataRepository,
    assemble_and_persist_moneyline_v1_feature_snapshot,
)


class MaterializationIdentityRepository(IdentityRepository, Protocol):
    def game_links(
        self,
        mapping_version: str,
    ) -> tuple[MLBGameIdentityLink, ...]: ...


class MaterializationFeatureRepository(Protocol):
    def append(self, snapshot: FeatureSnapshot) -> bool: ...

    def latest_for_game_version(
        self,
        *,
        game_id: str,
        feature_version: str,
        as_of: datetime,
    ) -> FeatureSnapshot | None: ...


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC)


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Official MLB first pitch must be timezone-aware")
    return parsed.astimezone(UTC)


def materialize_due_moneyline_v1_features(
    fixture_repository: FixtureRepository,
    identity_repository: MaterializationIdentityRepository,
    provider_repository: ProviderDataRepository,
    component_repository: ComponentRepository,
    feature_repository: MaterializationFeatureRepository,
    *,
    mapping_version: str,
    now: datetime,
    horizon_minutes: int = 150,
    max_games: int = 30,
    league_id: int = MLB_API_SPORTS_LEAGUE_ID,
    season: int | None = None,
) -> dict[str, int | str]:
    """Persist at most one Moneyline V1 feature snapshot per due linked game.

    This stage performs no provider calls. Games with incomplete point-in-time
    evidence fail closed and remain eligible for a later cycle.
    """

    if horizon_minutes < 1:
        raise ValueError("horizon_minutes must be positive")
    if max_games < 1:
        raise ValueError("max_games must be positive")

    current = _utc(now)
    links = identity_repository.game_links(mapping_version)
    due = tuple(
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
        "due_games": len(due),
        "already_materialized": 0,
        "games_considered": 0,
        "snapshots_inserted": 0,
        "evidence_blocked": 0,
        "due_games_unprocessed": 0,
        "provider_calls": 0,
    }
    if not due:
        return result

    pending: list[MLBGameIdentityLink] = []
    for link in due:
        existing = feature_repository.latest_for_game_version(
            game_id=link.game_id,
            feature_version=FEATURE_VERSION,
            as_of=current,
        )
        if existing is not None:
            result["already_materialized"] = int(result["already_materialized"]) + 1
        else:
            pending.append(link)

    selected = pending[:max_games]
    result["games_considered"] = len(selected)
    for link in selected:
        try:
            _, inserted = assemble_and_persist_moneyline_v1_feature_snapshot(
                fixture_repository,
                identity_repository,
                provider_repository,
                component_repository,
                feature_repository,
                provider_game_id=link.api_sports_provider_game_id,
                mapping_version=mapping_version,
                as_of=current,
                league_id=league_id,
                season=season,
            )
        except EvidenceError:
            result["evidence_blocked"] = int(result["evidence_blocked"]) + 1
            continue
        result["snapshots_inserted"] = int(result["snapshots_inserted"]) + int(
            inserted
        )

    unprocessed = max(0, len(pending) - len(selected))
    result["due_games_unprocessed"] = unprocessed

    if int(result["evidence_blocked"]) > 0:
        result["status"] = "BLOCKED_EVIDENCE"
    elif unprocessed > 0:
        result["status"] = "CAPACITY_LIMITED"
    else:
        result["status"] = "COMPLETE"
    return result
