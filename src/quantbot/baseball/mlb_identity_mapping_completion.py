"""Bounded completion of versioned MLB team identity mappings.

This boundary uses a durable API-Sports date-snapshot membership proof and one
official MLB schedule response for the same date. It only inserts team mappings;
it does not create game links or activate enrichment.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

from .evidence import EvidenceError
from .fixture_evidence import FixtureObservation
from .mlb_identity import MLBTeamIdentityMapping, propose_team_identity_mappings
from .official_mlb import OfficialMLBError
from .raw_archive import ArchiveReceipt


class MLBTeamMappingCompletionClient(Protocol):
    def schedule_identity_map_with_receipt(
        self,
        date_iso: str,
        *,
        captured_at: datetime | None = None,
    ) -> tuple[dict[str, Any], ArchiveReceipt]: ...


class MLBTeamMappingCompletionRepository(Protocol):
    def latest_mlb_fixtures_for_provider_query_date(
        self,
        *,
        date_iso: str,
        observed_by: datetime,
    ) -> tuple[FixtureObservation, ...]: ...

    def team_mappings(
        self,
        mapping_version: str,
    ) -> tuple[MLBTeamIdentityMapping, ...]: ...

    def append_team_mappings_atomically(
        self,
        records: tuple[MLBTeamIdentityMapping, ...],
    ) -> int: ...


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise EvidenceError("mapping completion timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise EvidenceError("mapping completion date must be YYYY-MM-DD") from exc


def _same_team_mapping(
    left: MLBTeamIdentityMapping,
    right: MLBTeamIdentityMapping,
) -> bool:
    return (
        left.api_sports_team_id == right.api_sports_team_id
        and left.official_mlb_team_id == right.official_mlb_team_id
        and left.api_sports_team_name.casefold()
        == right.api_sports_team_name.casefold()
        and left.official_mlb_team_name.casefold()
        == right.official_mlb_team_name.casefold()
    )


def complete_mlb_team_mappings(
    client: MLBTeamMappingCompletionClient,
    repository: MLBTeamMappingCompletionRepository,
    *,
    date_iso: str,
    mapping_version: str,
    now: datetime,
    kickoff_tolerance: timedelta = timedelta(minutes=30),
    expected_team_count: int = 30,
) -> dict[str, object]:
    """Fill missing team mappings from one exact durable provider-date snapshot."""

    if expected_team_count < 1:
        raise ValueError("expected_team_count must be positive")
    target_day = _date(date_iso)
    now = _utc(now)
    existing = repository.team_mappings(mapping_version)
    summary: dict[str, object] = {
        "status": "FAILED",
        "date": target_day.isoformat(),
        "mapping_version": mapping_version,
        "schedule_calls": 0,
        "fixtures_seen": 0,
        "candidate_fixtures": 0,
        "unmapped_team_ids_seen": [],
        "team_mappings_before": len(existing),
        "team_mappings_inserted": 0,
        "team_mappings_total": len(existing),
        "mapping_failures": 0,
        "failed_provider_game_ids": [],
        "ready_for_enrichment": 0,
    }
    if len(existing) >= expected_team_count:
        summary["status"] = "ALREADY_DONE"
        summary["ready_for_enrichment"] = 1
        return summary

    fixtures = repository.latest_mlb_fixtures_for_provider_query_date(
        date_iso=target_day.isoformat(),
        observed_by=now,
    )
    summary["fixtures_seen"] = len(fixtures)
    if not fixtures:
        summary["status"] = "NO_FIXTURES"
        return summary

    by_api = {row.api_sports_team_id: row for row in existing}
    by_mlb = {row.official_mlb_team_id: row for row in existing}
    unmapped_ids = {
        team_id
        for fixture in fixtures
        for team_id in (fixture.home_team_id, fixture.away_team_id)
        if team_id not in by_api
    }
    summary["unmapped_team_ids_seen"] = sorted(unmapped_ids)
    candidates = tuple(
        fixture
        for fixture in fixtures
        if fixture.home_team_id in unmapped_ids or fixture.away_team_id in unmapped_ids
    )
    summary["candidate_fixtures"] = len(candidates)
    if not candidates:
        summary["status"] = "NO_UNMAPPED_TEAMS_IN_SNAPSHOT"
        return summary

    try:
        payload, receipt = client.schedule_identity_map_with_receipt(
            target_day.isoformat(),
            captured_at=now,
        )
    except OfficialMLBError:
        summary["status"] = "SCHEDULE_ERROR"
        return summary
    summary["schedule_calls"] = 1

    proposed_by_api: dict[int, MLBTeamIdentityMapping] = {}
    proposed_by_mlb: dict[int, MLBTeamIdentityMapping] = {}
    failed_games: list[int] = []

    for fixture in candidates:
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
            failed_games.append(fixture.provider_game_id)
            continue

        fixture_failed = False
        for candidate in proposed:
            prior_api = by_api.get(candidate.api_sports_team_id)
            prior_mlb = by_mlb.get(candidate.official_mlb_team_id)
            if prior_api is not None and not _same_team_mapping(prior_api, candidate):
                fixture_failed = True
                break
            if prior_mlb is not None and not _same_team_mapping(prior_mlb, candidate):
                fixture_failed = True
                break

            pending_api = proposed_by_api.get(candidate.api_sports_team_id)
            pending_mlb = proposed_by_mlb.get(candidate.official_mlb_team_id)
            if pending_api is not None and not _same_team_mapping(pending_api, candidate):
                fixture_failed = True
                break
            if pending_mlb is not None and not _same_team_mapping(pending_mlb, candidate):
                fixture_failed = True
                break

            if prior_api is None:
                proposed_by_api[candidate.api_sports_team_id] = candidate
                proposed_by_mlb[candidate.official_mlb_team_id] = candidate

        if fixture_failed:
            failed_games.append(fixture.provider_game_id)

    failed_games = sorted(set(failed_games))
    summary["mapping_failures"] = len(failed_games)
    summary["failed_provider_game_ids"] = failed_games
    if failed_games:
        summary["status"] = "FAILED"
        return summary

    missing_proposals = unmapped_ids - proposed_by_api.keys()
    if missing_proposals:
        summary["mapping_failures"] = len(missing_proposals)
        summary["status"] = "FAILED"
        return summary

    records = tuple(
        proposed_by_api[team_id]
        for team_id in sorted(unmapped_ids)
    )
    summary["team_mappings_inserted"] = repository.append_team_mappings_atomically(
        records
    )
    mappings = repository.team_mappings(mapping_version)
    summary["team_mappings_total"] = len(mappings)
    ready = len(mappings) >= expected_team_count
    summary["ready_for_enrichment"] = int(ready)
    summary["status"] = "COMPLETE" if ready else "PARTIAL"
    return summary
