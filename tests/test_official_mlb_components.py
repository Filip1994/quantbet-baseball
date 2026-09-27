from datetime import UTC, datetime

import pytest

from quantbot.baseball.evidence import EvidenceError
from quantbot.baseball.official_mlb_components import build_pregame_components
from quantbot.baseball.raw_archive import ArchiveReceipt


def _payload():
    return {
        "gamePk": 823570,
        "metaData": {"timeStamp": "20260920_151258"},
        "gameData": {
            "datetime": {"dateTime": "2026-09-20T17:10:00Z"},
            "status": {
                "abstractGameState": "Preview",
                "detailedState": "Pre-Game",
            },
            "teams": {
                "away": {"id": 143, "name": "Philadelphia Phillies"},
                "home": {"id": 121, "name": "New York Mets"},
            },
            "probablePitchers": {
                "away": {"id": 650911, "fullName": "Cristopher Sánchez"},
                "home": {"id": 804636, "fullName": "Jonah Tong"},
            },
            "venue": {
                "id": 3289,
                "name": "Citi Field",
                "fieldInfo": {
                    "roofType": "Open",
                    "turfType": "Grass",
                    "leftLine": 335,
                    "leftCenter": 370,
                    "center": 408,
                    "rightCenter": 380,
                    "rightLine": 330,
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
                        "battingOrder": list(range(101, 110)),
                        "bullpen": [201, 202, 203],
                    },
                    "home": {
                        "battingOrder": list(range(301, 310)),
                        "bullpen": [401, 402, 403],
                    },
                }
            }
        },
    }


def _receipt():
    return ArchiveReceipt(
        ref="s3://raw/official-mlb/game-feed.json",
        checksum="a" * 64,
        captured_at=datetime(2026, 9, 20, 15, 13, tzinfo=UTC).isoformat(),
    )


def _by_key(rows):
    return {(row.component_type, row.side): row for row in rows}


def test_game_feed_splits_into_seven_point_in_time_components() -> None:
    rows = build_pregame_components(
        _payload(),
        _receipt(),
        requested_timecode="20260920_151000",
    )
    by_key = _by_key(rows)

    assert len(rows) == 7
    assert set(by_key) == {
        ("STARTER", "AWAY"),
        ("STARTER", "HOME"),
        ("LINEUP", "AWAY"),
        ("LINEUP", "HOME"),
        ("BULLPEN", "AWAY"),
        ("BULLPEN", "HOME"),
        ("VENUE", "GAME"),
    }

    away_starter = by_key[("STARTER", "AWAY")]
    assert away_starter.state == "PROBABLE"
    assert away_starter.data["pitcher_id"] == 650911
    assert away_starter.data["confirmation_state"] == "PROBABLE"
    assert away_starter.source_observed_at == "2026-09-20T15:12:58+00:00"

    home_lineup = by_key[("LINEUP", "HOME")]
    assert home_lineup.state == "POPULATED"
    assert len(home_lineup.data["batting_order_ids"]) == 9
    assert home_lineup.data["confirmation_state"] == "UNVERIFIED"

    away_bullpen = by_key[("BULLPEN", "AWAY")]
    assert away_bullpen.state == "PRESENT"
    assert away_bullpen.data["pitcher_ids"] == [201, 202, 203]

    venue = by_key[("VENUE", "GAME")]
    assert venue.state == "PRESENT"
    assert venue.data["venue_id"] == 3289
    assert venue.data["roof_type"] == "Open"
    assert venue.data["latitude"] == pytest.approx(40.75753012)

    assert all(row.requested_timecode == "20260920_151000" for row in rows)
    assert all(row.source_payload_ref == _receipt().ref for row in rows)
    assert not any(row.state == "CONFIRMED" for row in rows)


def test_absent_probable_pitcher_and_partial_lineup_are_explicit() -> None:
    payload = _payload()
    payload["gameData"]["probablePitchers"].pop("home")
    payload["liveData"]["boxscore"]["teams"]["home"]["battingOrder"] = [301, 302, 303]

    by_key = _by_key(build_pregame_components(payload, _receipt()))

    home_starter = by_key[("STARTER", "HOME")]
    assert home_starter.state == "ABSENT"
    assert home_starter.data["pitcher_id"] is None
    assert home_starter.data["confirmation_state"] == "ABSENT"

    home_lineup = by_key[("LINEUP", "HOME")]
    assert home_lineup.state == "PARTIAL"
    assert home_lineup.data["confirmation_state"] == "UNVERIFIED"


def test_component_builder_rejects_source_state_at_or_after_first_pitch() -> None:
    payload = _payload()
    payload["metaData"]["timeStamp"] = "20260920_171000"

    with pytest.raises(EvidenceError, match="must precede first pitch"):
        build_pregame_components(payload, _receipt())
