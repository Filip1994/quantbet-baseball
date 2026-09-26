import hashlib
import io
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from quantbot.baseball.evidence import EvidenceError
from quantbot.baseball.fixture_evidence import FixtureObservation
from quantbot.baseball.mlb_identity_diagnostic import (
    _read_verified_schedule_payload,
    diagnose_mlb_identity_coverage,
    diagnose_registry_gaps,
)


def _fixture(
    provider_game_id: int,
    *,
    home_id: int,
    home_name: str,
    away_id: int,
    away_name: str,
) -> FixtureObservation:
    return FixtureObservation(
        fixture_observation_id=f"00000000-0000-4000-8000-{provider_game_id:012d}",
        game_id=str(provider_game_id),
        provider="api-sports-baseball",
        provider_game_id=provider_game_id,
        league="MLB",
        home_team_id=home_id,
        home_team_name=home_name,
        away_team_id=away_id,
        away_team_name=away_name,
        kickoff_at="2026-09-26T23:10:00+00:00",
        provider_status="NS",
        observed_at="2026-09-26T17:00:00+00:00",
        source_payload_ref="s3://raw/api-sports/games.json",
        source_payload_checksum="a" * 64,
        schema_version="1.0",
    )


class FakeRepository:
    def __init__(self) -> None:
        self.fixtures = (
            _fixture(
                1001,
                home_id=1,
                home_name="Mapped Home",
                away_id=2,
                away_name="Mapped Away",
            ),
            _fixture(
                1002,
                home_id=3,
                home_name="Mapped Team",
                away_id=4,
                away_name="Missing Team",
            ),
        )
        self.mappings = (
            SimpleNamespace(api_sports_team_id=1),
            SimpleNamespace(api_sports_team_id=2),
            SimpleNamespace(api_sports_team_id=3),
        )

    def latest_mlb_fixtures_for_schedule_date(self, *, date_iso, observed_by):
        assert date_iso == "2026-09-26"
        assert observed_by.tzinfo is not None
        return self.fixtures

    def team_mappings(self, mapping_version):
        assert mapping_version == "mlb-2026-v1"
        return self.mappings

    def game_link_for_provider_game(self, *, mapping_version, provider_game_id):
        assert mapping_version == "mlb-2026-v1"
        if provider_game_id == 1001:
            return SimpleNamespace(
                api_sports_provider_game_id=1001,
                mlb_schedule_source_payload_ref="s3://raw/schedule.json",
                mlb_schedule_source_payload_checksum="b" * 64,
            )
        return None


def test_registry_gap_diagnostic_finds_missing_teams_and_name_drift() -> None:
    fixture = _fixture(
        1001,
        home_id=1,
        home_name="Mapped Home Renamed",
        away_id=2,
        away_name="Mapped Away",
    )
    mappings = (
        SimpleNamespace(
            api_sports_team_id=1,
            api_sports_team_name="Mapped Home",
            official_mlb_team_id=101,
            official_mlb_team_name="Official Home",
        ),
        SimpleNamespace(
            api_sports_team_id=2,
            api_sports_team_name="Mapped Away",
            official_mlb_team_id=102,
            official_mlb_team_name="Official Away",
        ),
    )
    standings = [
        {
            "team_id": 1,
            "team_name": "Mapped Home Renamed",
            "observed_at": "2026-09-26T14:00:00+00:00",
            "source_payload_ref": "s3://raw/standings.json",
            "source_payload_checksum": "c" * 64,
        },
        {
            "team_id": 2,
            "team_name": "Mapped Away",
            "observed_at": "2026-09-26T14:00:00+00:00",
            "source_payload_ref": "s3://raw/standings.json",
            "source_payload_checksum": "c" * 64,
        },
        {
            "team_id": 3,
            "team_name": "Missing Club",
            "observed_at": "2026-09-26T14:00:00+00:00",
            "source_payload_ref": "s3://raw/standings.json",
            "source_payload_checksum": "c" * 64,
        },
    ]

    result = diagnose_registry_gaps(
        standings=standings,
        mappings=mappings,
        fixtures=(fixture,),
    )

    assert result["registry_team_universe_total"] == 3
    assert result["missing_registry_mappings_count"] == 1
    assert result["missing_registry_mappings"][0]["api_sports_team_id"] == 3
    assert result["missing_registry_mappings"][0]["api_sports_team_name"] == "Missing Club"
    assert result["current_api_name_drifts_count"] == 1
    assert result["current_api_name_drifts"][0]["api_sports_team_id"] == 1
    assert (
        result["current_api_name_drifts"][0]["mapped_api_sports_team_name"]
        == "Mapped Home"
    )
    assert (
        result["current_api_name_drifts"][0]["current_api_sports_team_name"]
        == "Mapped Home Renamed"
    )


def test_identity_diagnostic_is_read_only_coverage_evidence() -> None:
    result = diagnose_mlb_identity_coverage(
        FakeRepository(),
        date_iso="2026-09-26",
        mapping_version="mlb-2026-v1",
        observed_by=datetime(2026, 9, 26, 17, 30, tzinfo=UTC),
    )

    assert result["status"] == "INCOMPLETE"
    assert result["provider_calls"] == 0
    assert result["fixtures_seen"] == 2
    assert result["team_mappings_total"] == 3
    assert result["game_links_total_for_target"] == 1
    assert result["unresolved_fixtures_count"] == 1
    assert result["unresolved_fixtures"] == [
        {
            "provider_game_id": 1002,
            "kickoff_at": "2026-09-26T23:10:00+00:00",
            "provider_status": "NS",
            "observed_at": "2026-09-26T17:00:00+00:00",
            "home_team_id": 3,
            "home_team_name": "Mapped Team",
            "away_team_id": 4,
            "away_team_name": "Missing Team",
            "source_payload_ref": "s3://raw/api-sports/games.json",
            "source_payload_checksum": "a" * 64,
            "link_present": False,
            "missing_team_mappings": [
                {
                    "side": "away",
                    "api_sports_team_id": 4,
                    "api_sports_team_name": "Missing Team",
                }
            ],
            "reason_code": "MISSING_TEAM_MAPPING",
        }
    ]


class _FakeS3Client:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def get_object(self, **kwargs):
        assert kwargs == {"Bucket": "raw", "Key": "schedule.json"}
        return {"Body": io.BytesIO(self.body)}


def _schedule_archive_document() -> bytes:
    document = {
        "captured_at": "2026-09-26T17:31:15+00:00",
        "endpoint": "official-mlb/v1/schedule",
        "params": {
            "sportId": "1",
            "date": "2026-09-26",
            "hydrate": "probablePitcher,team,venue",
        },
        "payload": {"dates": []},
    }
    return json.dumps(
        document,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def test_schedule_archive_read_requires_matching_checksum_and_provenance() -> None:
    body = _schedule_archive_document()
    archive = SimpleNamespace(bucket="raw", client=_FakeS3Client(body))

    payload = _read_verified_schedule_payload(
        archive,
        source_payload_ref="s3://raw/schedule.json",
        source_payload_checksum=hashlib.sha256(body).hexdigest(),
        date_iso="2026-09-26",
    )

    assert payload == {"dates": []}

    with pytest.raises(EvidenceError, match="checksum mismatch"):
        _read_verified_schedule_payload(
            archive,
            source_payload_ref="s3://raw/schedule.json",
            source_payload_checksum="0" * 64,
            date_iso="2026-09-26",
        )
