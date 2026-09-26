"""Read-only replay diagnostics for MLB team-mapping completion failures."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from .evidence import EvidenceError
from .fixture_evidence import FixtureObservation
from .mlb_identity import diagnose_fixture_schedule_match
from .mlb_identity_repository import PostgreSQLMLBIdentityRepository
from .raw_archive import S3RawPayloadArchive, archive_from_env

_SCHEDULE_ENDPOINT = "official-mlb/v1/schedule"
_SCHEDULE_HYDRATE = "probablePitcher,team,venue"
_CHECKSUM_SUFFIX = re.compile(r"_([0-9a-f]{12})\.json$")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise EvidenceError("mapping diagnostic timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _schedule_params(date_iso: str) -> dict[str, str]:
    try:
        date.fromisoformat(date_iso)
    except ValueError as exc:
        raise EvidenceError("mapping diagnostic date must be YYYY-MM-DD") from exc
    return {
        "sportId": "1",
        "date": date_iso,
        "hydrate": _SCHEDULE_HYDRATE,
    }


def _request_digest(date_iso: str) -> str:
    params = _schedule_params(date_iso)
    request_identity = json.dumps(
        [
            _SCHEDULE_ENDPOINT,
            sorted((str(key), str(value)) for key, value in params.items()),
        ],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(request_identity).hexdigest()[:12]


def _read_body(value: Any) -> bytes:
    body = value.read() if hasattr(value, "read") else value
    if not isinstance(body, (bytes, bytearray)):
        raise EvidenceError("archive body must be bytes")
    return bytes(body)


def _list_schedule_keys(
    archive: S3RawPayloadArchive,
    *,
    observed_by: datetime,
    request_digest: str,
) -> list[tuple[datetime, str]]:
    needle = f"_official-mlb_v1_schedule_{request_digest}_"
    results: list[tuple[datetime, str]] = []
    for offset in (0, 1):
        day = (observed_by.date() - timedelta(days=offset)).isoformat()
        prefix = f"api-sports-baseball/{day}/"
        token: str | None = None
        while True:
            kwargs: dict[str, Any] = {
                "Bucket": archive.bucket,
                "Prefix": prefix,
                "MaxKeys": 1000,
            }
            if token:
                kwargs["ContinuationToken"] = token
            response = archive.client.list_objects_v2(**kwargs)
            for item in response.get("Contents") or ():
                key = str(item.get("Key") or "")
                if needle not in key:
                    continue
                modified = item.get("LastModified")
                if not isinstance(modified, datetime):
                    raise EvidenceError("archive listing LastModified is invalid")
                results.append((_utc(modified), key))
            if not response.get("IsTruncated"):
                break
            token = str(response.get("NextContinuationToken") or "")
            if not token:
                raise EvidenceError("archive listing pagination token is missing")
    return sorted(results, reverse=True)


def _latest_verified_schedule_archive(
    archive: S3RawPayloadArchive,
    *,
    date_iso: str,
    observed_by: datetime,
) -> tuple[dict[str, Any], dict[str, str]]:
    observed_by = _utc(observed_by)
    expected_params = _schedule_params(date_iso)
    keys = _list_schedule_keys(
        archive,
        observed_by=observed_by,
        request_digest=_request_digest(date_iso),
    )
    if not keys:
        raise EvidenceError("matching official MLB schedule archive was not found")

    for modified, key in keys:
        if modified > observed_by:
            continue
        response = archive.client.get_object(Bucket=archive.bucket, Key=key)
        body = _read_body(response.get("Body"))
        checksum = hashlib.sha256(body).hexdigest()
        suffix = _CHECKSUM_SUFFIX.search(key)
        if suffix is None or not checksum.startswith(suffix.group(1)):
            raise EvidenceError("schedule archive checksum disagrees with object key")
        try:
            document = json.loads(body)
        except json.JSONDecodeError as exc:
            raise EvidenceError("schedule archive is invalid JSON") from exc
        if not isinstance(document, dict):
            raise EvidenceError("schedule archive document must be an object")
        if document.get("endpoint") != _SCHEDULE_ENDPOINT:
            continue
        params = document.get("params")
        if not isinstance(params, dict):
            continue
        normalized_params = {str(key): str(value) for key, value in params.items()}
        if normalized_params != expected_params:
            continue
        captured_raw = str(document.get("captured_at") or "")
        try:
            captured = _utc(datetime.fromisoformat(captured_raw))
        except (ValueError, EvidenceError) as exc:
            raise EvidenceError("schedule archive captured_at is invalid") from exc
        if captured > observed_by:
            continue
        payload = document.get("payload")
        if not isinstance(payload, dict):
            raise EvidenceError("schedule archive payload must be an object")
        return payload, {
            "source_payload_ref": f"s3://{archive.bucket}/{key}",
            "source_payload_checksum": checksum,
            "captured_at": captured.isoformat(),
        }
    raise EvidenceError("verified official MLB schedule archive was not found")


def _fixture_row(
    fixture: FixtureObservation,
    *,
    mapped_team_ids: set[int],
    schedule_payload: dict[str, Any],
) -> dict[str, object]:
    missing = [
        {
            "side": side,
            "api_sports_team_id": getattr(fixture, f"{side}_team_id"),
            "api_sports_team_name": getattr(fixture, f"{side}_team_name"),
        }
        for side in ("home", "away")
        if getattr(fixture, f"{side}_team_id") not in mapped_team_ids
    ]
    return {
        "provider_game_id": fixture.provider_game_id,
        "kickoff_at": fixture.kickoff_at,
        "observed_at": fixture.observed_at,
        "provider_status": fixture.provider_status,
        "home_team_id": fixture.home_team_id,
        "home_team_name": fixture.home_team_name,
        "away_team_id": fixture.away_team_id,
        "away_team_name": fixture.away_team_name,
        "source_payload_ref": fixture.source_payload_ref,
        "source_payload_checksum": fixture.source_payload_checksum,
        "missing_team_mappings": missing,
        "schedule_match_diagnostic": diagnose_fixture_schedule_match(
            fixture,
            schedule_payload,
        ),
    }


def run_mlb_mapping_completion_diagnostic(
    database_url: str,
    *,
    date_iso: str,
    mapping_version: str,
    observed_by: datetime,
    root: Path | None = None,
) -> dict[str, object]:
    """Replay the last matching schedule archive without contacting any provider."""

    import psycopg

    observed_by = _utc(observed_by)
    with psycopg.connect(database_url) as connection:
        repository = PostgreSQLMLBIdentityRepository(connection)
        fixtures = repository.latest_mlb_fixtures_for_provider_query_date(
            date_iso=date_iso,
            observed_by=observed_by,
        )
        mappings = repository.team_mappings(mapping_version)

    mapped_team_ids = {row.api_sports_team_id for row in mappings}
    unmapped_team_ids = sorted(
        {
            team_id
            for fixture in fixtures
            for team_id in (fixture.home_team_id, fixture.away_team_id)
            if team_id not in mapped_team_ids
        }
    )
    candidates = tuple(
        fixture
        for fixture in fixtures
        if fixture.home_team_id in unmapped_team_ids
        or fixture.away_team_id in unmapped_team_ids
    )
    result: dict[str, object] = {
        "status": "FAILED",
        "date": date_iso,
        "mapping_version": mapping_version,
        "provider_calls": 0,
        "archive_reads": 0,
        "fixtures_seen": len(fixtures),
        "team_mappings_total": len(mappings),
        "unmapped_team_ids_seen": unmapped_team_ids,
        "candidate_fixtures_count": len(candidates),
        "candidate_fixtures": [],
    }
    if not candidates:
        result["status"] = "NO_CANDIDATES"
        return result

    try:
        archive = archive_from_env(
            (root or Path.cwd()) / "data/baseball/raw",
            require_remote=True,
        )
        if not isinstance(archive, S3RawPayloadArchive):
            raise EvidenceError("remote S3 archive is required")
        payload, evidence = _latest_verified_schedule_archive(
            archive,
            date_iso=date_iso,
            observed_by=observed_by,
        )
    except Exception as exc:  # noqa: BLE001 - diagnostic must fail closed
        result["status"] = "ARCHIVE_READ_FAILED"
        result["error_type"] = type(exc).__name__
        return result

    result["archive_reads"] = 1
    result["schedule_archive"] = evidence
    rows = [
        _fixture_row(
            fixture,
            mapped_team_ids=mapped_team_ids,
            schedule_payload=payload,
        )
        for fixture in candidates
    ]
    result["candidate_fixtures"] = rows
    result["status"] = "COMPLETE"
    return result
