"""Incremental official MLB game identity linking.

The 30-team registry is treated as immutable input here. This stage only links
new API-Sports MLB fixtures to official MLB gamePk values and never mutates team
identity mappings.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

from .evidence import EvidenceError
from .fixture_evidence import FixtureObservation
from .mlb_identity import (
    MLBGameIdentityLink,
    MLBTeamIdentityMapping,
    MLBTeamIdentityRegistry,
    link_fixture_to_mlb_game,
)
from .official_mlb import OfficialMLBError
from .raw_archive import ArchiveReceipt


class MLBGameLinkingClient(Protocol):
    def schedule_identity_map_with_receipt(
        self,
        date_iso: str,
        *,
        captured_at: datetime | None = None,
    ) -> tuple[dict[str, Any], ArchiveReceipt]: ...


class MLBGameLinkingRepository(Protocol):
    def latest_mlb_fixtures_for_schedule_date(
        self,
        *,
        date_iso: str,
        observed_by: datetime,
    ) -> tuple[FixtureObservation, ...]: ...

    def team_mappings(
        self,
        mapping_version: str,
    ) -> tuple[MLBTeamIdentityMapping, ...]: ...

    def game_link_for_provider_game(
        self,
        *,
        mapping_version: str,
        provider_game_id: int,
    ) -> MLBGameIdentityLink | None: ...

    def append_game_link(self, record: MLBGameIdentityLink) -> bool: ...


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise EvidenceError("game-linking timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise EvidenceError("game-linking date must be YYYY-MM-DD") from exc


def collect_mlb_game_links(
    client: MLBGameLinkingClient,
    repository: MLBGameLinkingRepository,
    *,
    date_iso: str,
    mapping_version: str,
    now: datetime,
    kickoff_tolerance: timedelta = timedelta(minutes=30),
    expected_team_count: int = 30,
) -> dict[str, int | str]:
    """Link one MLB slate against the completed team registry.

    Once every fixture in the target slate is linked, repeated runs perform
    zero official MLB schedule calls.
    """

    if expected_team_count < 1:
        raise ValueError("expected_team_count must be positive")
    target_day = _date(date_iso)
    current = _utc(now)
    mappings = repository.team_mappings(mapping_version)
    result: dict[str, int | str] = {
        "status": "BLOCKED",
        "date": target_day.isoformat(),
        "mapping_version": mapping_version,
        "schedule_calls": 0,
        "fixtures_seen": 0,
        "fixtures_already_linked": 0,
        "team_mappings_total": len(mappings),
        "game_links_inserted": 0,
        "game_links_total_for_target": 0,
        "link_failures": 0,
        "ready_for_enrichment": 0,
    }
    if len(mappings) < expected_team_count:
        result["status"] = "TEAM_REGISTRY_INCOMPLETE"
        return result

    try:
        registry = MLBTeamIdentityRegistry(mappings)
    except EvidenceError:
        result["status"] = "TEAM_REGISTRY_INVALID"
        return result

    fixtures = repository.latest_mlb_fixtures_for_schedule_date(
        date_iso=target_day.isoformat(),
        observed_by=current,
    )
    result["fixtures_seen"] = len(fixtures)
    if not fixtures:
        result["status"] = "NO_FIXTURES"
        return result

    existing = {
        fixture.provider_game_id: repository.game_link_for_provider_game(
            mapping_version=mapping_version,
            provider_game_id=fixture.provider_game_id,
        )
        for fixture in fixtures
    }
    already_linked = sum(link is not None for link in existing.values())
    result["fixtures_already_linked"] = already_linked
    result["game_links_total_for_target"] = already_linked

    if already_linked == len(fixtures):
        result["status"] = "ALREADY_DONE"
        result["ready_for_enrichment"] = 1
        return result

    try:
        payload, receipt = client.schedule_identity_map_with_receipt(
            target_day.isoformat(),
            captured_at=current,
        )
    except OfficialMLBError:
        result["status"] = "SCHEDULE_ERROR"
        return result
    result["schedule_calls"] = 1

    linked_total = already_linked
    for fixture in fixtures:
        if existing[fixture.provider_game_id] is not None:
            continue
        try:
            link = link_fixture_to_mlb_game(
                fixture,
                payload,
                receipt,
                registry,
                linked_at=current,
                kickoff_tolerance=kickoff_tolerance,
            )
        except EvidenceError:
            result["link_failures"] = int(result["link_failures"]) + 1
            continue
        if repository.append_game_link(link):
            result["game_links_inserted"] = int(result["game_links_inserted"]) + 1
        linked_total += 1

    result["game_links_total_for_target"] = linked_total
    complete = linked_total == len(fixtures) and int(result["link_failures"]) == 0
    result["ready_for_enrichment"] = int(complete)
    result["status"] = "COMPLETE" if complete else "PARTIAL"
    return result
