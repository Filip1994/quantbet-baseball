"""Bounded historical pregame canary for Official MLB enrichment."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from .evidence import EvidenceError
from .mlb_identity import MLBGameIdentityLink, MLBTeamIdentityMapping
from .official_mlb import (
    OfficialMLBError,
    OfficialMLBStatsClient,
    canonical_pregame_snapshot,
)
from .official_mlb_component_repository import PostgreSQLOfficialMLBComponentRepository
from .official_mlb_components import (
    OfficialMLBPregameComponent,
    build_pregame_components,
)
from .raw_archive import archive_from_env

_EXPECTED_COMPONENT_KEYS = {
    ("STARTER", "AWAY"),
    ("STARTER", "HOME"),
    ("LINEUP", "AWAY"),
    ("LINEUP", "HOME"),
    ("BULLPEN", "AWAY"),
    ("BULLPEN", "HOME"),
    ("VENUE", "GAME"),
}


class EnrichmentCanaryClient(Protocol):
    def game_feed_with_receipt(
        self,
        game_pk: int,
        *,
        timecode: str | None = None,
        captured_at: datetime | None = None,
    ): ...


class EnrichmentCanaryIdentityRepository(Protocol):
    def team_mappings(
        self,
        mapping_version: str,
    ) -> tuple[MLBTeamIdentityMapping, ...]: ...

    def game_links(
        self,
        mapping_version: str,
    ) -> tuple[MLBGameIdentityLink, ...]: ...


class EnrichmentCanaryComponentRepository(Protocol):
    def components_for_requested_timecode(
        self,
        *,
        mlb_game_pk: int,
        requested_timecode: str,
    ) -> tuple[OfficialMLBPregameComponent, ...]: ...

    def append_components(
        self,
        records: tuple[OfficialMLBPregameComponent, ...],
    ) -> int: ...


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError("identity link first pitch must be timezone-aware")
    return parsed.astimezone(UTC)


def _component_keys(
    rows: tuple[OfficialMLBPregameComponent, ...],
) -> set[tuple[str, str]]:
    return {(row.component_type, row.side) for row in rows}


def _is_complete_component_set(
    rows: tuple[OfficialMLBPregameComponent, ...],
) -> bool:
    return len(rows) == 7 and _component_keys(rows) == _EXPECTED_COMPONENT_KEYS


def run_enrichment_canary_with_dependencies(
    client: EnrichmentCanaryClient,
    identity_repository: EnrichmentCanaryIdentityRepository,
    component_repository: EnrichmentCanaryComponentRepository,
    *,
    mapping_version: str,
    now: datetime,
    expected_team_count: int = 30,
) -> dict[str, object]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    current = now.astimezone(UTC)
    mappings = identity_repository.team_mappings(mapping_version)
    result: dict[str, object] = {
        "status": "BLOCKED",
        "mapping_version": mapping_version,
        "provider_calls": 0,
        "team_mappings_total": len(mappings),
        "game_links_total": 0,
        "components_before": 0,
        "components_inserted": 0,
        "components_total": 0,
        "point_in_time_eligible": 0,
    }
    if len(mappings) < expected_team_count:
        result["reason_codes"] = ["TEAM_REGISTRY_INCOMPLETE"]
        return result

    links = identity_repository.game_links(mapping_version)
    result["game_links_total"] = len(links)
    if not links:
        result["reason_codes"] = ["NO_VERIFIED_GAME_LINKS"]
        return result

    link = links[-1]
    first_pitch = _timestamp(link.official_mlb_first_pitch)
    requested_at = first_pitch - timedelta(hours=2)
    requested_timecode = requested_at.strftime("%Y%m%d_%H%M%S")
    result.update(
        {
            "provider_game_id": link.api_sports_provider_game_id,
            "mlb_game_pk": link.mlb_game_pk,
            "official_first_pitch": first_pitch.isoformat(),
            "requested_timecode": requested_timecode,
        }
    )

    existing = component_repository.components_for_requested_timecode(
        mlb_game_pk=link.mlb_game_pk,
        requested_timecode=requested_timecode,
    )
    result["components_before"] = len(existing)
    if existing:
        if _is_complete_component_set(existing):
            result["status"] = "ALREADY_DONE"
            result["components_total"] = len(existing)
            result["point_in_time_eligible"] = int(
                all(
                    _timestamp(row.source_observed_at) < first_pitch
                    for row in existing
                )
            )
            return result
        result["reason_codes"] = ["PARTIAL_EXISTING_COMPONENT_SET"]
        return result

    try:
        payload, receipt = client.game_feed_with_receipt(
            link.mlb_game_pk,
            timecode=requested_timecode,
            captured_at=current,
        )
        result["provider_calls"] = 1
        snapshot = canonical_pregame_snapshot(
            payload,
            receipt,
            requested_timecode=requested_timecode,
        )
    except (OfficialMLBError, EvidenceError, ValueError) as exc:
        result["status"] = "FAILED"
        result["reason_codes"] = [type(exc).__name__]
        return result

    if (
        snapshot.mlb_game_pk != link.mlb_game_pk
        or snapshot.home_team_id != link.mlb_home_team_id
        or snapshot.away_team_id != link.mlb_away_team_id
    ):
        result["status"] = "FAILED"
        result["reason_codes"] = ["GAME_IDENTITY_MISMATCH"]
        return result

    rows = build_pregame_components(
        payload,
        receipt,
        requested_timecode=requested_timecode,
    )
    if not _is_complete_component_set(rows):
        result["status"] = "FAILED"
        result["reason_codes"] = ["COMPONENT_SET_INCOMPLETE"]
        return result

    inserted = component_repository.append_components(rows)
    readback = component_repository.components_for_requested_timecode(
        mlb_game_pk=link.mlb_game_pk,
        requested_timecode=requested_timecode,
    )
    eligible = (
        _is_complete_component_set(readback)
        and all(_timestamp(row.source_observed_at) < first_pitch for row in readback)
    )
    result.update(
        {
            "status": "COMPLETE" if eligible else "FAILED",
            "components_inserted": inserted,
            "components_total": len(readback),
            "point_in_time_eligible": int(eligible),
            "source_observed_at": (
                readback[0].source_observed_at if readback else None
            ),
            "component_states": {
                f"{row.component_type}:{row.side}": row.state
                for row in readback
            },
            "reason_codes": [] if eligible else ["READBACK_INCOMPLETE"],
        }
    )
    return result


def run_official_mlb_enrichment_canary(
    database_url: str,
    *,
    mapping_version: str,
    now: datetime,
    root: Path | None = None,
) -> dict[str, object]:
    import psycopg

    from .mlb_identity_repository import PostgreSQLMLBIdentityRepository

    archive = archive_from_env(
        (root or Path.cwd()) / "data/baseball/raw",
        require_remote=True,
    )
    client = OfficialMLBStatsClient(raw_archive=archive)
    with psycopg.connect(database_url) as connection:
        identity_repository = PostgreSQLMLBIdentityRepository(connection)
        component_repository = PostgreSQLOfficialMLBComponentRepository(connection)
        return run_enrichment_canary_with_dependencies(
            client,
            identity_repository,
            component_repository,
            mapping_version=mapping_version,
            now=now,
        )
