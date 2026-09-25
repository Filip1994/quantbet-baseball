from quantbot.baseball.fixture_evidence import canonical_fixture_observation
from quantbot.baseball.raw_archive import ArchiveReceipt


def receipt():
    return ArchiveReceipt(
        ref="s3://raw/games/2030-09-18.json",
        checksum="b" * 64,
        captured_at="2030-09-18T17:00:00+00:00",
    )


def game():
    return {
        "id": 10,
        "date": "2030-09-18T19:00:00+00:00",
        "status": {"short": "NS"},
        "league": {"name": "MLB"},
        "teams": {
            "home": {"id": 101, "name": "Home Club"},
            "away": {"id": 202, "name": "Away Club"},
        },
    }


def test_maps_provider_game_to_canonical_fixture_observation() -> None:
    row = canonical_fixture_observation(game(), receipt())

    assert row is not None
    assert row.game_id == "10"
    assert row.provider_game_id == 10
    assert row.home_team_id == 101
    assert row.away_team_id == 202
    assert row.kickoff_at == "2030-09-18T19:00:00+00:00"
    assert row.provider_status == "NS"
    assert row.source_payload_checksum == "b" * 64


def test_exact_replay_has_same_identity() -> None:
    first = canonical_fixture_observation(game(), receipt())
    replay = canonical_fixture_observation(game(), receipt())

    assert first is not None
    assert replay is not None
    assert first == replay
    assert first.fixture_observation_id == replay.fixture_observation_id


def test_missing_provider_team_identity_fails_closed() -> None:
    malformed = game()
    del malformed["teams"]["away"]["id"]

    assert canonical_fixture_observation(malformed, receipt()) is None
