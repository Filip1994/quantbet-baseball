from quantbot.baseball.operational import fixture_observation_from_game
from quantbot.baseball.raw_archive import ArchiveReceipt


def _receipt() -> ArchiveReceipt:
    return ArchiveReceipt(
        ref="s3://raw/games-2030-09-18.json",
        checksum="b" * 64,
        captured_at="2030-09-18T17:00:00+00:00",
    )


def _game(status="NS"):
    return {
        "id": 10,
        "date": "2030-09-18T19:00:00+00:00",
        "teams": {
            "home": {"name": "Home Club"},
            "away": {"name": "Away Club"},
        },
        "league": {"name": "MLB"},
        "status": {"short": status},
    }


def test_fixture_observation_is_deterministic() -> None:
    first = fixture_observation_from_game(_game(), _receipt())
    replay = fixture_observation_from_game(_game(), _receipt())

    assert first is not None
    assert first == replay
    assert first.fixture_observation_id == replay.fixture_observation_id
    assert first.game_id == "10"
    assert first.provider_status == "NS"


def test_status_change_creates_new_fixture_observation() -> None:
    scheduled = fixture_observation_from_game(_game("NS"), _receipt())
    postponed = fixture_observation_from_game(_game("PST"), _receipt())

    assert scheduled is not None
    assert postponed is not None
    assert scheduled.fixture_observation_id != postponed.fixture_observation_id


def test_incomplete_fixture_fails_closed() -> None:
    game = _game()
    game["teams"]["away"]["name"] = ""

    assert fixture_observation_from_game(game, _receipt()) is None
