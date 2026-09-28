"""Restart-safe materialization for league-agnostic Moneyline core features."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from .evidence import EvidenceError
from .feature_snapshot import FeatureSnapshot
from .fixture_evidence import FixtureObservation
from .moneyline_features import (
    CORE_FEATURE_VERSION,
    FixtureRepository,
    ProviderDataRepository,
    assemble_and_persist_moneyline_core_v1_feature_snapshot,
)


class CoreFixtureRepository(FixtureRepository, Protocol):
    def latest_due_core_fixtures(
        self,
        *,
        as_of: datetime,
        horizon_minutes: int,
    ) -> tuple[FixtureObservation, ...]: ...


class CoreFeatureRepository(Protocol):
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


def materialize_due_moneyline_core_v1_features(
    fixture_repository: CoreFixtureRepository,
    provider_repository: ProviderDataRepository,
    feature_repository: CoreFeatureRepository,
    *,
    now: datetime,
    league_ids: tuple[int, ...] | None = None,
    horizon_minutes: int = 150,
    max_games: int = 30,
    season: int | None = None,
) -> dict[str, int | str]:
    """Persist CORE snapshots for due games using only already-stored PIT evidence."""

    if horizon_minutes < 1:
        raise ValueError("horizon_minutes must be positive")
    if max_games < 1:
        raise ValueError("max_games must be positive")
    if league_ids is not None and not league_ids:
        raise ValueError("league_ids cannot be empty when provided")

    current = _utc(now)
    due = fixture_repository.latest_due_core_fixtures(
        as_of=current,
        horizon_minutes=horizon_minutes,
    )

    result: dict[str, int | str] = {
        "status": "NO_DUE_GAMES",
        "league_ids": (
            "dynamic"
            if league_ids is None
            else ",".join(str(value) for value in league_ids)
        ),
        "due_games": len(due),
        "already_materialized": 0,
        "games_considered": 0,
        "snapshots_inserted": 0,
        "evidence_blocked": 0,
        "unsupported_league": 0,
        "due_games_unprocessed": 0,
        "provider_calls": 0,
    }
    if not due:
        return result

    pending: list[FixtureObservation] = []
    for fixture in due:
        existing = feature_repository.latest_for_game_version(
            game_id=fixture.game_id,
            feature_version=CORE_FEATURE_VERSION,
            as_of=current,
        )
        if existing is not None:
            result["already_materialized"] = int(result["already_materialized"]) + 1
        else:
            pending.append(fixture)

    selected = pending[:max_games]
    result["games_considered"] = len(selected)
    for fixture in selected:
        league_id = fixture.league_id
        if league_id is None:
            result["unsupported_league"] = int(result["unsupported_league"]) + 1
            continue
        if league_ids is not None and league_id not in league_ids:
            result["unsupported_league"] = int(result["unsupported_league"]) + 1
            continue
        try:
            _, inserted = assemble_and_persist_moneyline_core_v1_feature_snapshot(
                fixture_repository,
                provider_repository,
                feature_repository,
                provider_game_id=fixture.provider_game_id,
                as_of=current,
                league_id=league_id,
                season=season,
            )
        except EvidenceError:
            result["evidence_blocked"] = int(result["evidence_blocked"]) + 1
            continue
        result["snapshots_inserted"] = int(result["snapshots_inserted"]) + int(inserted)

    unprocessed = max(0, len(pending) - len(selected))
    result["due_games_unprocessed"] = unprocessed

    if int(result["evidence_blocked"]) > 0 or int(result["unsupported_league"]) > 0:
        result["status"] = "BLOCKED_EVIDENCE"
    elif unprocessed > 0:
        result["status"] = "CAPACITY_LIMITED"
    else:
        result["status"] = "COMPLETE"
    return result
