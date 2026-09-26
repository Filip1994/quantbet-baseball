"""Bounded official MLB identity bootstrap.

This boundary uses the official MLB schedule only to prove API-Sports fixture
identity. It does not canonicalize MLB schedule/results and does not activate
official MLB pregame enrichment.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Protocol

from .evidence import EvidenceError
from .fixture_evidence import FixtureObservation
from .mlb_identity import (
    MLBGameIdentityLink,
    MLBTeamIdentityMapping,
    MLBTeamIdentityRegistry,
    link_fixture_to_mlb_game,
    propose_team_identity_mappings,
)
from .raw_archive import ArchiveReceipt


class MLBIdentityBootstrapClient(Protocol):
    def schedule_identity_map_with_receipt(
        self,
        date_iso: str,
        *,
        captured_at: datetime | None = None,
    ) -> tuple[dict[str, Any], ArchiveReceipt]: ...


class MLBIdentityBootstrapRepository(Protocol):
    def latest_mlb_fixtures_around_date(
        self,
        *,
        date_iso: str,
        observed_by: datetime,
        padding: timedelta,
    ) -> tuple[FixtureObservation, ...]: ...

    def team_mappings(self, mapping_version: str) -> tuple[MLBTeamIdentityMapping, ...]:
        ...

    def append_team_mapping(self, record: MLBTeamIdentityMapping) -> bool: ...

    def game_link_for_provider_game(
        self,
        *,
        mapping_version: str,
        provider_game_id: int,
    ) -> MLBGameIdentityLink | None: ...

    def append_game_link(self, record: MLBGameIdentityLink) -> bool: ...


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise EvidenceError("identity bootstrap timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise EvidenceError("identity bootstrap date must be YYYY-MM-DD") from exc


def _same_team_mapping(
    left: MLBTeamIdentityMapping,
    right: MLBTeamIdentityMapping,
) -> bool:
    return (
        left.api_sports_team_id == right.api_sports_team_id
        and left.official_mlb_team_id == right.official_mlb_team_id
        and left.api_sports_team_name.casefold() == right.api_sports_team_name.casefold()
        and left.official_mlb_team_name.casefold()
        == right.official_mlb_team_name.casefold()
    )


def collect_mlb_identity_bootstrap(
    client: MLBIdentityBootstrapClient,
    repository: MLBIdentityBootstrapRepository,
    *,
    date_iso: str,
    mapping_version: str,
    now: datetime,
    kickoff_tolerance: timedelta = timedelta(minutes=30),
    expected_team_count: int = 30,
) -> dict[str, int | str]:
    """Run one archived schedule identity proof or fail closed.

    A fully-linked target date is idempotent and performs zero MLB schedule calls.
    """

    if expected_team_count < 1:
        raise ValueError("expected_team_count must be positive")
    target_day = _date(date_iso)
    now = _utc(now)
    fixtures = repository.latest_mlb_fixtures_around_date(
        date_iso=target_day.isoformat(),
        observed_by=now,
        padding=timedelta(hours=12),
    )
    existing_links = {
        fixture.provider_game_id: repository.game_link_for_provider_game(
            mapping_version=mapping_version,
            provider_game_id=fixture.provider_game_id,
        )
        for fixture in fixtures
    }
    already_linked = sum(link is not None for link in existing_links.values())
    existing_mappings = repository.team_mappings(mapping_version)

    summary: dict[str, int | str] = {
        "status": "FAILED",
        "date": target_day.isoformat(),
        "mapping_version": mapping_version,
        "schedule_calls": 0,
        "fixtures_seen": len(fixtures),
        "fixtures_already_linked": already_linked,
        "team_mappings_before": len(existing_mappings),
        "team_mappings_inserted": 0,
        "team_mappings_total": len(existing_mappings),
        "game_links_inserted": 0,
        "game_links_total_for_target": already_linked,
        "mapping_failures": 0,
        "link_failures": 0,
        "ready_for_enrichment": 0,
    }
    if not fixtures:
        summary["status"] = "NO_FIXTURES"
        return summary

    if already_linked == len(fixtures):
        summary["status"] = "ALREADY_DONE"
        summary["ready_for_enrichment"] = int(
            len(existing_mappings) >= expected_team_count
        )
        return summary

    payload, receipt = client.schedule_identity_map_with_receipt(
        target_day.isoformat(),
        captured_at=now,
    )
    summary["schedule_calls"] = 1

    by_api = {row.api_sports_team_id: row for row in existing_mappings}
    by_mlb = {row.official_mlb_team_id: row for row in existing_mappings}

    for fixture in fixtures:
        try:
            proposed = propose_team_identity_mappings(
                fixture,
                payload,
                receipt,
                mapping_version=mapping_version,
                verified_at=now,
                kickoff_tolerance=kickoff_tolerance,
            )
        except EvidenceError:
            summary["mapping_failures"] = int(summary["mapping_failures"]) + 1
            continue

        for candidate in proposed:
            prior_api = by_api.get(candidate.api_sports_team_id)
            prior_mlb = by_mlb.get(candidate.official_mlb_team_id)
            if prior_api is not None and not _same_team_mapping(prior_api, candidate):
                summary["mapping_failures"] = int(summary["mapping_failures"]) + 1
                continue
            if prior_mlb is not None and not _same_team_mapping(prior_mlb, candidate):
                summary["mapping_failures"] = int(summary["mapping_failures"]) + 1
                continue
            if prior_api is not None:
                continue
            if repository.append_team_mapping(candidate):
                summary["team_mappings_inserted"] = (
                    int(summary["team_mappings_inserted"]) + 1
                )
            by_api[candidate.api_sports_team_id] = candidate
            by_mlb[candidate.official_mlb_team_id] = candidate

    mappings = repository.team_mappings(mapping_version)
    summary["team_mappings_total"] = len(mappings)
    try:
        registry = MLBTeamIdentityRegistry(mappings)
    except EvidenceError:
        summary["status"] = "FAILED"
        return summary

    linked_total = 0
    for fixture in fixtures:
        existing = repository.game_link_for_provider_game(
            mapping_version=mapping_version,
            provider_game_id=fixture.provider_game_id,
        )
        if existing is not None:
            linked_total += 1
            continue
        try:
            link = link_fixture_to_mlb_game(
                fixture,
                payload,
                receipt,
                registry,
                linked_at=now,
                kickoff_tolerance=kickoff_tolerance,
            )
        except EvidenceError:
            summary["link_failures"] = int(summary["link_failures"]) + 1
            continue
        if repository.append_game_link(link):
            summary["game_links_inserted"] = int(summary["game_links_inserted"]) + 1
        linked_total += 1

    summary["game_links_total_for_target"] = linked_total
    failures = int(summary["mapping_failures"]) + int(summary["link_failures"])
    complete_target = linked_total == len(fixtures)
    ready = (
        failures == 0
        and complete_target
        and len(mappings) >= expected_team_count
    )
    summary["ready_for_enrichment"] = int(ready)
    summary["status"] = "COMPLETE" if complete_target and failures == 0 else "PARTIAL"
    return summary
