from datetime import UTC, datetime

from quantbot.baseball.official_mlb import canonical_pregame_snapshot
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
                "away": {"id": 650911, "fullName": "Cristopher Sanchez"},
                "home": {"id": 804636, "fullName": "Jonah Tong"},
            },
            "venue": {
                "id": 3289,
                "name": "Citi Field",
                "fieldInfo": {},
                "location": {},
                "timeZone": {},
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
                        "bullpen": [],
                    },
                    "home": {
                        "battingOrder": [201, 202, 203],
                        "bullpen": [],
                    },
                }
            }
        },
    }


def _snapshot(*, captured_at="2026-09-20T15:20:00+00:00"):
    return canonical_pregame_snapshot(
        _payload(),
        ArchiveReceipt(
            ref="s3://raw/mlb-feed.json",
            checksum="a" * 64,
            captured_at=captured_at,
        ),
        requested_timecode="20260920_151000",
    )


def test_components_preserve_probable_and_nonconfirmed_semantics() -> None:
    starters, lineups = build_pregame_components(_snapshot())
    away_starter, home_starter = starters
    away_lineup, home_lineup = lineups

    assert away_starter.side == "AWAY"
    assert away_starter.starter_state == "PROBABLE"
    assert away_starter.pitcher_id == 650911
    assert home_starter.starter_state == "PROBABLE"
    assert home_starter.pitcher_id == 804636

    assert away_lineup.lineup_state == "POPULATED"
    assert away_lineup.confirmation_state == "NOT_ASSERTED"
    assert away_lineup.batting_order_ids == tuple(range(101, 110))
    assert home_lineup.lineup_state == "PARTIAL"
    assert home_lineup.confirmation_state == "NOT_ASSERTED"
    assert home_lineup.batting_order_ids == (201, 202, 203)

    assert away_starter.source_observed_at == "2026-09-20T15:12:58+00:00"
    assert away_starter.retrieved_at == "2026-09-20T15:20:00+00:00"
    assert away_starter.requested_timecode == "20260920_151000"
    assert away_starter.source_payload_ref == "s3://raw/mlb-feed.json"
    assert away_starter.source_payload_checksum == "a" * 64


def test_missing_probable_pitcher_is_absent_not_confirmed_or_guessed() -> None:
    payload = _payload()
    payload["gameData"]["probablePitchers"].pop("home")
    snapshot = canonical_pregame_snapshot(
        payload,
        ArchiveReceipt(
            ref="s3://raw/mlb-feed-missing-starter.json",
            checksum="b" * 64,
            captured_at=datetime(2026, 9, 20, 15, 20, tzinfo=UTC).isoformat(),
        ),
    )

    starters, _ = build_pregame_components(snapshot)
    home = starters[1]

    assert home.side == "HOME"
    assert home.starter_state == "ABSENT"
    assert home.pitcher_id is None
    assert home.pitcher_name is None


def test_historical_backfill_can_be_retrieved_after_pitch_without_claiming_live_knowledge() -> (
    None
):
    snapshot = _snapshot(captured_at="2026-09-21T12:00:00+00:00")
    starters, lineups = build_pregame_components(snapshot)

    assert starters[0].source_observed_at == "2026-09-20T15:12:58+00:00"
    assert starters[0].retrieved_at == "2026-09-21T12:00:00+00:00"
    assert lineups[0].retrieved_at == "2026-09-21T12:00:00+00:00"
