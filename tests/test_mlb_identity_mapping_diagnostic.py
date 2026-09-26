import hashlib
import json
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from quantbot.baseball.fixture_evidence import FixtureObservation
from quantbot.baseball.mlb_identity_mapping_diagnostic import (
    _fixture_row,
    _latest_verified_schedule_archive,
    _request_digest,
)
from quantbot.baseball.raw_archive import S3RawPayloadArchive


def _document(*, captured_at="2026-09-26T23:30:47+00:00"):
    return {
        "captured_at": captured_at,
        "endpoint": "official-mlb/v1/schedule",
        "params": {
            "sportId": "1",
            "date": "2026-09-27",
            "hydrate": "probablePitcher,team,venue",
        },
        "payload": {
            "dates": [
                {
                    "date": "2026-09-27",
                    "games": [
                        {
                            "gamePk": 900010,
                            "gameDate": "2026-09-27T17:05:00Z",
                            "teams": {
                                "home": {
                                    "team": {
                                        "id": 147,
                                        "name": "New York Yankees",
                                    }
                                },
                                "away": {
                                    "team": {
                                        "id": 110,
                                        "name": "Baltimore Orioles",
                                    }
                                },
                            },
                        },
                        {
                            "gamePk": 900011,
                            "gameDate": "2026-09-27T19:05:00Z",
                            "teams": {
                                "home": {
                                    "team": {
                                        "id": 111,
                                        "name": "Boston Red Sox",
                                    }
                                },
                                "away": {
                                    "team": {
                                        "id": 112,
                                        "name": "Chicago Cubs",
                                    }
                                },
                            },
                        },
                    ],
                }
            ]
        },
    }


class FakeS3Client:
    def __init__(self, key, body):
        self.key = key
        self.body = body

    def list_objects_v2(self, **kwargs):
        if self.key.startswith(kwargs["Prefix"]):
            return {
                "IsTruncated": False,
                "Contents": [
                    {
                        "Key": self.key,
                        "LastModified": datetime(2026, 9, 26, 23, 30, 48, tzinfo=UTC),
                    }
                ],
            }
        return {"IsTruncated": False, "Contents": []}

    def get_object(self, **kwargs):
        assert kwargs["Key"] == self.key
        return {"Body": BytesIO(self.body)}


def _archive():
    body = json.dumps(
        _document(),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    checksum = hashlib.sha256(body).hexdigest()
    digest = _request_digest("2026-09-27")
    key = (
        "api-sports-baseball/2026-09-26/"
        f"20260926T233047.000000Z_official-mlb_v1_schedule_{digest}_"
        f"{checksum[:12]}.json"
    )
    return S3RawPayloadArchive(
        client=FakeS3Client(key, body),
        bucket="raw-bucket",
    ), checksum


def _fixture(*, game_id, home_id, home_name, away_id, away_name, kickoff):
    return FixtureObservation(
        fixture_observation_id=f"00000000-0000-4000-8000-{game_id:012d}",
        game_id=str(game_id),
        provider="api-sports-baseball",
        provider_game_id=game_id,
        league="MLB",
        home_team_id=home_id,
        home_team_name=home_name,
        away_team_id=away_id,
        away_team_name=away_name,
        kickoff_at=kickoff,
        provider_status="NS",
        observed_at="2026-09-26T23:30:40+00:00",
        source_payload_ref="s3://raw/provider-date.json",
        source_payload_checksum="a" * 64,
        schema_version="1.0",
    )


def test_archive_replay_reads_matching_schedule_once() -> None:
    archive, checksum = _archive()

    payload, evidence = _latest_verified_schedule_archive(
        archive,
        date_iso="2026-09-27",
        observed_by=datetime(2026, 9, 26, 23, 31, tzinfo=UTC),
    )

    assert payload == _document()["payload"]
    assert evidence["source_payload_checksum"] == checksum
    assert evidence["source_payload_ref"].startswith("s3://raw-bucket/")


def test_candidate_diagnostic_distinguishes_exact_and_first_pitch_mismatch() -> None:
    payload = _document()["payload"]
    exact = _fixture(
        game_id=200001,
        home_id=25,
        home_name="New York Yankees",
        away_id=4,
        away_name="Baltimore Orioles",
        kickoff="2026-09-27T17:05:00+00:00",
    )
    mismatch = _fixture(
        game_id=200002,
        home_id=5,
        home_name="Boston Red Sox",
        away_id=6,
        away_name="Chicago Cubs",
        kickoff="2026-09-26T23:15:00+00:00",
    )

    exact_row = _fixture_row(
        exact,
        mapped_team_ids=set(),
        schedule_payload=payload,
    )
    mismatch_row = _fixture_row(
        mismatch,
        mapped_team_ids=set(),
        schedule_payload=payload,
    )

    assert (
        exact_row["schedule_match_diagnostic"]["classification"]
        == "EXACT_MATCH_AVAILABLE"
    )
    assert (
        mismatch_row["schedule_match_diagnostic"]["classification"]
        == "FIRST_PITCH_MISMATCH"
    )
    candidate = mismatch_row["schedule_match_diagnostic"]["candidate_games"][0]
    assert candidate["mlb_game_pk"] == 900011
    assert candidate["kickoff_delta_seconds"] > 1800


def test_request_digest_matches_raw_archive_identity_contract() -> None:
    assert _request_digest("2026-09-27") == "3908599d0267"
