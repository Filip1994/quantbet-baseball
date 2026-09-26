"""Read-only diagnostics for durable MLB identity coverage."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .fixture_evidence import FixtureObservation
from .mlb_identity import MLBGameIdentityLink, MLBTeamIdentityMapping


class MLBIdentityDiagnosticRepository(Protocol):
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


def diagnose_mlb_identity_coverage(
    repository: MLBIdentityDiagnosticRepository,
    *,
    date_iso: str,
    mapping_version: str,
    observed_by: datetime,
) -> dict[str, object]:
    """Describe unresolved identity rows without contacting any provider."""

    fixtures = repository.latest_mlb_fixtures_for_schedule_date(
        date_iso=date_iso,
        observed_by=observed_by,
    )
    mappings = repository.team_mappings(mapping_version)
    mapped_team_ids = {row.api_sports_team_id for row in mappings}

    links_total = 0
    unresolved: list[dict[str, object]] = []
    for fixture in fixtures:
        link = repository.game_link_for_provider_game(
            mapping_version=mapping_version,
            provider_game_id=fixture.provider_game_id,
        )
        if link is not None:
            links_total += 1

        missing: list[dict[str, object]] = []
        if fixture.home_team_id not in mapped_team_ids:
            missing.append(
                {
                    "side": "home",
                    "api_sports_team_id": fixture.home_team_id,
                    "api_sports_team_name": fixture.home_team_name,
                }
            )
        if fixture.away_team_id not in mapped_team_ids:
            missing.append(
                {
                    "side": "away",
                    "api_sports_team_id": fixture.away_team_id,
                    "api_sports_team_name": fixture.away_team_name,
                }
            )

        if missing or link is None:
            unresolved.append(
                {
                    "provider_game_id": fixture.provider_game_id,
                    "kickoff_at": fixture.kickoff_at,
                    "home_team_id": fixture.home_team_id,
                    "home_team_name": fixture.home_team_name,
                    "away_team_id": fixture.away_team_id,
                    "away_team_name": fixture.away_team_name,
                    "link_present": link is not None,
                    "missing_team_mappings": missing,
                    "reason_code": (
                        "MISSING_TEAM_MAPPING"
                        if missing
                        else "UNLINKED_WITH_COMPLETE_TEAM_MAPPING"
                    ),
                }
            )

    return {
        "status": "COMPLETE" if not unresolved else "INCOMPLETE",
        "date": date_iso,
        "mapping_version": mapping_version,
        "provider_calls": 0,
        "fixtures_seen": len(fixtures),
        "team_mappings_total": len(mappings),
        "game_links_total_for_target": links_total,
        "unresolved_fixtures_count": len(unresolved),
        "unresolved_fixtures": unresolved,
    }


def run_mlb_identity_diagnostic(
    database_url: str,
    *,
    date_iso: str,
    mapping_version: str,
    observed_by: datetime,
) -> dict[str, object]:
    """Run the diagnostic against PostgreSQL using read-only repository methods."""

    import psycopg

    from .mlb_identity_repository import PostgreSQLMLBIdentityRepository

    with psycopg.connect(database_url) as connection:
        repository = PostgreSQLMLBIdentityRepository(connection)
        return diagnose_mlb_identity_coverage(
            repository,
            date_iso=date_iso,
            mapping_version=mapping_version,
            observed_by=observed_by,
        )
