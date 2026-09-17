from quantbot.baseball.ingestion import canonical_moneyline_observations
from quantbot.baseball.raw_archive import ArchiveReceipt


def snapshot(
    *,
    market: str = "Moneyline",
    selection: str = "Home",
    odd: str = "1.91",
    captured: str = "2026-09-18T17:00:00+00:00",
):
    return {
        "captured_at": captured,
        "game_id": 123,
        "kickoff": "2026-09-18T19:00:00+00:00",
        "home": "Home Club",
        "away": "Away Club",
        "odds": {
            "bookmakers": [
                {
                    "name": "bet365",
                    "markets": [
                        {
                            "name": market,
                            "values": [{"value": selection, "odd": odd}],
                        }
                    ],
                }
            ]
        },
    }


def receipt(captured: str = "2026-09-18T17:00:00+00:00") -> ArchiveReceipt:
    return ArchiveReceipt(
        ref="s3://raw/example.json",
        checksum="a" * 64,
        captured_at=captured,
    )


def test_maps_supported_full_game_moneyline() -> None:
    rows = canonical_moneyline_observations(snapshot(), receipt())

    assert len(rows) == 1
    row = rows[0]
    assert row.game_id == "123"
    assert row.market_family == "moneyline"
    assert row.selection == "home"
    assert row.bookmaker == "bet365"
    assert row.decimal_odds == 1.91
    assert row.line is None
    assert row.source_payload_checksum == "a" * 64


def test_maps_team_name_to_away_side() -> None:
    rows = canonical_moneyline_observations(
        snapshot(selection="Away Club", odd="2.15"),
        receipt(),
    )

    assert len(rows) == 1
    assert rows[0].selection == "away"


def test_rejects_non_full_game_winner_market() -> None:
    rows = canonical_moneyline_observations(
        snapshot(market="Winner - First Five Innings"),
        receipt(),
    )

    assert rows == ()


def test_replay_is_idempotent_and_new_capture_has_new_identity() -> None:
    first = canonical_moneyline_observations(snapshot(), receipt())[0]
    replay = canonical_moneyline_observations(snapshot(), receipt())[0]
    later_receipt = receipt("2026-09-18T17:15:00+00:00")
    later = canonical_moneyline_observations(
        snapshot(captured=later_receipt.captured_at),
        later_receipt,
    )[0]

    assert first == replay
    assert first.observation_id == replay.observation_id
    assert first.observation_id != later.observation_id


def test_post_kickoff_observation_is_rejected() -> None:
    late = receipt("2026-09-18T19:00:00+00:00")

    assert canonical_moneyline_observations(
        snapshot(captured=late.captured_at),
        late,
    ) == ()
