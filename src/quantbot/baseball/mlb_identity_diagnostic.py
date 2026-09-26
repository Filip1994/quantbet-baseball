"""Read-only diagnostics for durable MLB identity coverage."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from .evidence import EvidenceError
from .fixture_evidence import FixtureObservation
from .mlb_identity import (
    MLBGameIdentityLink,
    MLBTeamIdentityMapping,
    diagnose_fixture_schedule_match,
)
from .raw_archive import S3RawPayloadArchive, archive_from_env


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
    linked_schedule_archives: set[tuple[str, str]] = set()
    unresolved: list[dict[str, object]] = []
    for fixture in fixtures:
        link = repository.game_link_for_provider_game(
            mapping_version=mapping_version,
            provider_game_id=fixture.provider_game_id,
        )
        if link is not None:
            links_total += 1
            linked_schedule_archives.add(
                (
                    link.mlb_schedule_source_payload_ref,
                    link.mlb_schedule_source_payload_checksum,
                )
            )

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
                    "provider_status": fixture.provider_status,
                    "observed_at": fixture.observed_at,
                    "home_team_id": fixture.home_team_id,
                    "home_team_name": fixture.home_team_name,
                    "away_team_id": fixture.away_team_id,
                    "away_team_name": fixture.away_team_name,
                    "source_payload_ref": fixture.source_payload_ref,
                    "source_payload_checksum": fixture.source_payload_checksum,
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
        "linked_schedule_archives": [
            {"source_payload_ref": ref, "source_payload_checksum": checksum}
            for ref, checksum in sorted(linked_schedule_archives)
        ],
        "unresolved_fixtures_count": len(unresolved),
        "unresolved_fixtures": unresolved,
    }


def diagnose_registry_gaps(
    *,
    standings: list[dict[str, object]],
    mappings: tuple[MLBTeamIdentityMapping, ...],
    fixtures: tuple[FixtureObservation, ...],
) -> dict[str, object]:
    """Compare the canonical 30-team provider universe with versioned mappings."""

    mapped_by_api = {row.api_sports_team_id: row for row in mappings}
    missing: list[dict[str, object]] = []
    for row in standings:
        team_id = int(row["team_id"])
        if team_id in mapped_by_api:
            continue
        missing.append(
            {
                "api_sports_team_id": team_id,
                "api_sports_team_name": str(row["team_name"]),
                "standing_observed_at": str(row["observed_at"]),
                "source_payload_ref": str(row["source_payload_ref"]),
                "source_payload_checksum": str(row["source_payload_checksum"]),
            }
        )

    drifts: list[dict[str, object]] = []
    seen_drift: set[tuple[int, str]] = set()
    for fixture in fixtures:
        for side in ("home", "away"):
            team_id = getattr(fixture, f"{side}_team_id")
            current_name = getattr(fixture, f"{side}_team_name")
            mapping = mapped_by_api.get(team_id)
            if mapping is None:
                continue
            if mapping.api_sports_team_name.casefold() == current_name.casefold():
                continue
            key = (team_id, current_name.casefold())
            if key in seen_drift:
                continue
            seen_drift.add(key)
            drifts.append(
                {
                    "api_sports_team_id": team_id,
                    "mapped_api_sports_team_name": mapping.api_sports_team_name,
                    "current_api_sports_team_name": current_name,
                    "official_mlb_team_id": mapping.official_mlb_team_id,
                    "official_mlb_team_name": mapping.official_mlb_team_name,
                    "provider_game_id": fixture.provider_game_id,
                    "side": side,
                    "fixture_observed_at": fixture.observed_at,
                    "fixture_source_payload_ref": fixture.source_payload_ref,
                    "fixture_source_payload_checksum": fixture.source_payload_checksum,
                }
            )

    return {
        "registry_team_universe_total": len(standings),
        "missing_registry_mappings_count": len(missing),
        "missing_registry_mappings": missing,
        "current_api_name_drifts_count": len(drifts),
        "current_api_name_drifts": drifts,
    }


def _read_verified_schedule_payload(
    archive: S3RawPayloadArchive,
    *,
    source_payload_ref: str,
    source_payload_checksum: str,
    date_iso: str,
) -> dict[str, Any]:
    """Read one previously archived MLB schedule document and verify provenance."""

    parsed = urlsplit(source_payload_ref)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
        raise EvidenceError("MLB schedule archive reference must be an s3 URI")
    if parsed.netloc != archive.bucket:
        raise EvidenceError(
            "MLB schedule archive bucket disagrees with configured bucket"
        )

    key = parsed.path.lstrip("/")
    result = archive.client.get_object(Bucket=archive.bucket, Key=key)
    body = result["Body"].read()
    if hashlib.sha256(body).hexdigest() != source_payload_checksum:
        raise EvidenceError("MLB schedule archive checksum mismatch")

    try:
        document = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError("MLB schedule archive is not valid JSON") from exc
    if not isinstance(document, dict):
        raise EvidenceError("MLB schedule archive document must be an object")
    if document.get("endpoint") != "official-mlb/v1/schedule":
        raise EvidenceError("MLB schedule archive endpoint is unexpected")

    params = document.get("params")
    if not isinstance(params, dict):
        raise EvidenceError("MLB schedule archive params must be an object")
    if str(params.get("sportId") or "") != "1":
        raise EvidenceError("MLB schedule archive sportId is unexpected")
    if str(params.get("date") or "") != date_iso:
        raise EvidenceError(
            "MLB schedule archive date disagrees with diagnostic target"
        )

    payload = document.get("payload")
    if not isinstance(payload, dict):
        raise EvidenceError("MLB schedule archive payload must be an object")
    return payload


def run_mlb_identity_diagnostic(
    database_url: str,
    *,
    date_iso: str,
    mapping_version: str,
    observed_by: datetime,
    root: Path | None = None,
) -> dict[str, object]:
    """Run DB coverage plus checksum-verified archive-only root-cause diagnostics."""

    import psycopg

    from .mlb_identity_repository import PostgreSQLMLBIdentityRepository

    with psycopg.connect(database_url) as connection:
        repository = PostgreSQLMLBIdentityRepository(connection)
        result = diagnose_mlb_identity_coverage(
            repository,
            date_iso=date_iso,
            mapping_version=mapping_version,
            observed_by=observed_by,
        )
        fixtures = repository.latest_mlb_fixtures_for_schedule_date(
            date_iso=date_iso,
            observed_by=observed_by,
        )
        mappings = repository.team_mappings(mapping_version)
        season = date.fromisoformat(date_iso).year
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT ON (team_id)
                    team_id,
                    team_name,
                    observed_at,
                    source_payload_ref,
                    source_payload_checksum
                FROM api_sports_standing_snapshots
                WHERE league_id = 1
                  AND season = %s
                  AND observed_at <= %s
                ORDER BY team_id, observed_at DESC, snapshot_id DESC
                """,
                (season, observed_by),
            )
            standing_rows = [
                {
                    "team_id": row[0],
                    "team_name": row[1],
                    "observed_at": row[2].isoformat(),
                    "source_payload_ref": row[3],
                    "source_payload_checksum": row[4],
                }
                for row in cursor.fetchall()
            ]
        result.update(
            diagnose_registry_gaps(
                standings=standing_rows,
                mappings=mappings,
                fixtures=fixtures,
            )
        )

    result["archive_reads"] = 0
    if int(result["unresolved_fixtures_count"]) == 0:
        result["archive_diagnostic_status"] = "NOT_NEEDED"
        return result

    schedule_archives = result.get("linked_schedule_archives")
    if not isinstance(schedule_archives, list) or len(schedule_archives) != 1:
        result["archive_diagnostic_status"] = "SCHEDULE_EVIDENCE_NOT_UNIQUE"
        return result
    evidence = schedule_archives[0]
    if not isinstance(evidence, dict):
        result["archive_diagnostic_status"] = "SCHEDULE_EVIDENCE_INVALID"
        return result

    try:
        archive = archive_from_env(
            (root or Path.cwd()) / "data/baseball/raw",
            require_remote=True,
        )
        if not isinstance(archive, S3RawPayloadArchive):
            raise EvidenceError("remote S3 archive is required")
        payload = _read_verified_schedule_payload(
            archive,
            source_payload_ref=str(evidence.get("source_payload_ref") or ""),
            source_payload_checksum=str(evidence.get("source_payload_checksum") or ""),
            date_iso=date_iso,
        )
    except Exception as exc:  # noqa: BLE001 - diagnostic must fail closed
        result["archive_diagnostic_status"] = "ARCHIVE_READ_FAILED"
        result["archive_diagnostic_error_type"] = type(exc).__name__
        return result

    result["archive_reads"] = 1
    result["archive_diagnostic_status"] = "COMPLETE"
    fixture_by_game = {fixture.provider_game_id: fixture for fixture in fixtures}
    unresolved = result.get("unresolved_fixtures")
    if not isinstance(unresolved, list):
        result["archive_diagnostic_status"] = "UNRESOLVED_EVIDENCE_INVALID"
        return result

    for row in unresolved:
        if not isinstance(row, dict):
            continue
        fixture = fixture_by_game.get(int(row["provider_game_id"]))
        if fixture is None:
            row["schedule_match_diagnostic"] = {"classification": "FIXTURE_NOT_FOUND"}
            continue
        row["schedule_match_diagnostic"] = diagnose_fixture_schedule_match(
            fixture,
            payload,
        )
    return result
