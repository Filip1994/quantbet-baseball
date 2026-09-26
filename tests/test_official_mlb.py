import json
from datetime import UTC, datetime

import pytest

from quantbot.baseball.evidence import EvidenceError
from quantbot.baseball.official_mlb import (
    OfficialMLBStatsClient,
    canonical_pregame_snapshot,
)
from quantbot.baseball.raw_archive import ArchiveReceipt, LocalRawPayloadArchive


def _payload():
    return {
        "gamePk": 823570,
        "metaData": {"timeStamp": "20260920_151258"},
        "gameData": {
            "datetime": {
                "dateTime": "2026-09-20T17:10:00Z",
                "dayNight": "day",
            },
            "status": {
                "abstractGameState": "Preview",
                "detailedState": "Pre-Game",
            },
            "teams": {
                "away": {
                    "id": 143,
                    "name": "Philadelphia Phillies",
                    "record": {
                        "wins": 86,
                        "losses": 70,
                        "gamesPlayed": 156,
                        "winningPercentage": ".551",
                    },
                },
                "home": {
                    "id": 121,
                    "name": "New York Mets",
                    "record": {
                        "wins": 71,
                        "losses": 85,
                        "gamesPlayed": 156,
                        "winningPercentage": ".455",
                    },
                },
            },
            "probablePitchers": {
                "away": {"id": 650911, "fullName": "Cristopher Sánchez"},
                "home": {"id": 804636, "fullName": "Jonah Tong"},
            },
            "venue": {
                "id": 3289,
                "name": "Citi Field",
                "fieldInfo": {
                    "leftLine": 335,
                    "leftCenter": 370,
                    "center": 408,
                    "rightCenter": 380,
                    "rightLine": 330,
                    "roofType": "Open",
                    "turfType": "Grass",
                },
                "location": {
                    "elevation": 10,
                    "azimuthAngle": 13.0,
                    "defaultCoordinates": {
                        "latitude": 40.75753012,
                        "longitude": -73.84559155,
                    },
                },
                "timeZone": {
                    "id": "America/New_York",
                    "offsetAtGameTime": -4,
                },
            },
        },
        "liveData": {
            "boxscore": {
                "teams": {
                    "away": {
                        "battingOrder": [
                            101,
                            102,
                            103,
                            104,
                            105,
                            106,
                            107,
                            108,
                            109,
                        ],
                        "bullpen": [201, 202, 203],
                    },
                    "home": {
                        "battingOrder": [
                            301,
                            302,
                            303,
                            304,
                            305,
                            306,
                            307,
                            308,
                            309,
                        ],
                        "bullpen": [401, 402, 403],
                    },
                }
            }
        },
    }


def _receipt(captured_at="2026-09-26T08:00:00+00:00"):
    return ArchiveReceipt(
        ref="s3://raw/mlb-feed.json",
        checksum="a" * 64,
        captured_at=captured_at,
    )


def test_canonical_snapshot_uses_actual_provider_metadata_cutoff() -> None:
    snapshot = canonical_pregame_snapshot(
        _payload(),
        _receipt(),
        requested_timecode="20260920_151000",
    )

    assert snapshot.mlb_game_pk == 823570
    assert snapshot.source_observed_at == "2026-09-20T15:12:58+00:00"
    assert snapshot.requested_timecode == "20260920_151000"
    assert snapshot.source_observed_at != "2026-09-20T15:10:00+00:00"
    assert snapshot.scheduled_first_pitch == "2026-09-20T17:10:00+00:00"
    assert snapshot.away_probable_pitcher_id == 650911
    assert snapshot.home_probable_pitcher_id == 804636
    assert snapshot.lineup_state == "POPULATED"
    assert len(snapshot.away_batting_order_ids) == 9
    assert len(snapshot.home_batting_order_ids) == 9
    assert snapshot.roof_type == "Open"
    assert snapshot.elevation_ft == 10.0
    assert snapshot.latitude == pytest.approx(40.75753012)
    assert snapshot.longitude == pytest.approx(-73.84559155)
    assert snapshot.field_azimuth_deg == 13.0
    assert snapshot.venue_timezone == "America/New_York"
    assert snapshot.venue_utc_offset_at_game == -4.0


def test_lineup_presence_does_not_claim_confirmation() -> None:
    snapshot = canonical_pregame_snapshot(_payload(), _receipt())

    assert snapshot.lineup_state == "POPULATED"
    assert not hasattr(snapshot, "lineup_confirmed")


def test_snapshot_rejects_provider_state_at_or_after_first_pitch() -> None:
    payload = _payload()
    payload["metaData"]["timeStamp"] = "20260920_171000"

    with pytest.raises(EvidenceError, match="must precede first pitch"):
        canonical_pregame_snapshot(payload, _receipt())


def test_client_archives_feed_and_keeps_timecode_separate_from_cutoff(tmp_path) -> None:
    calls = []

    def transport(url):
        calls.append(url)
        return _payload()

    client = OfficialMLBStatsClient(
        raw_archive=LocalRawPayloadArchive(tmp_path),
        transport=transport,
    )
    snapshot = client.pregame_snapshot(
        823570,
        timecode="20260920_151000",
        captured_at=datetime(2026, 9, 26, 8, 0, tzinfo=UTC),
    )

    assert len(calls) == 1
    assert "timecode=20260920_151000" in calls[0]
    assert snapshot.source_payload_ref.startswith("file://")
    assert len(snapshot.source_payload_checksum) == 64
    assert snapshot.source_observed_at == "2026-09-20T15:12:58+00:00"
    archived = json.loads(next(tmp_path.rglob("*.json")).read_text(encoding="utf-8"))
    assert archived["endpoint"].endswith("/feed/live")
    assert archived["params"] == {"timecode": "20260920_151000"}
