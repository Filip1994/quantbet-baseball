from datetime import UTC, datetime, timedelta

from quantbot.baseball.game_history_collection import collect_game_history
from quantbot.baseball.raw_archive import ArchiveReceipt


def _row(game_id: int = 1) -> dict:
    return {
        "id": game_id,
        "date": "2026-09-20T17:00:00+00:00",
        "timezone": "UTC",
        "status": {"long": "Finished", "short": "FT"},
        "league": {"id": 1, "season": 2026},
        "teams": {
            "home": {"id": 10, "name": "Home"},
            "away": {"id": 20, "name": "Away"},
        },
        "scores": {
            "home": {
                "hits": 10,
                "errors": 0,
                "innings": {"1": 1, "9": 0, "extra": None},
                "total": 5,
            },
            "away": {
                "hits": 8,
                "errors": 1,
                "innings": {"1": 0, "9": 0, "extra": None},
                "total": 3,
            },
        },
    }


class FakeClient:
    def __init__(self) -> None:
        self.request_count = 0
        self.remaining_budget = 10
        self.calls = 0

    def games_by_league_season_with_receipt(self, league_id, season):
        self.request_count += 1
        self.remaining_budget -= 1
        self.calls += 1
        assert (league_id, season) == (1, 2026)
        return (
            [_row()],
            ArchiveReceipt(
                ref="s3://raw/history.json",
                checksum="a" * 64,
                captured_at="2026-09-26T08:00:00+00:00",
            ),
        )


class FakeRepository:
    def __init__(self, latest=None) -> None:
        self.latest = latest
        self.records = []

    def latest_observed_at(self, *, league_id, season):
        assert (league_id, season) == (1, 2026)
        return self.latest

    def append_snapshots(self, records):
        records = tuple(records)
        self.records.extend(records)
        return len(records)


def test_game_history_collection_uses_one_request_and_archived_rows() -> None:
    client = FakeClient()
    repository = FakeRepository()

    result = collect_game_history(
        client,
        repository,
        now=datetime(2026, 9, 26, 9, 0, tzinfo=UTC),
        max_requests=1,
    )

    assert result["requests"] == 1
    assert result["calls"] == 1
    assert result["rows"] == 1
    assert result["inserted"] == 1
    assert client.calls == 1
    assert repository.records[0].provider_game_id == 1


def test_game_history_collection_is_not_repolled_before_daily_cadence() -> None:
    now = datetime(2026, 9, 26, 9, 0, tzinfo=UTC)
    client = FakeClient()
    repository = FakeRepository(latest=now - timedelta(hours=6))

    result = collect_game_history(
        client,
        repository,
        now=now,
        max_requests=1,
    )

    assert result["requests"] == 0
    assert result["calls"] == 0
    assert client.calls == 0


def test_game_history_collection_honors_zero_leftover_budget() -> None:
    client = FakeClient()
    repository = FakeRepository()

    result = collect_game_history(
        client,
        repository,
        now=datetime(2026, 9, 26, 9, 0, tzinfo=UTC),
        max_requests=0,
    )

    assert result["request_cap"] == 0
    assert result["requests"] == 0
    assert client.calls == 0
