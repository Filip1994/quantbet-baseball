from datetime import UTC, datetime, timedelta

from quantbot.baseball.provider_data import canonical_standings
from quantbot.baseball.raw_archive import ArchiveReceipt
from quantbot.baseball.slow_provider_collection import collect_slow_provider_data


def _receipt(name, captured_at="2026-09-26T08:00:00+00:00"):
    return ArchiveReceipt(
        ref=f"s3://raw/{name}.json",
        checksum=(name[0] if name else "a") * 64,
        captured_at=captured_at,
    )


def _team_stats(team_id):
    return {
        "team": {"id": team_id, "name": f"Team {team_id}"},
        "league": {"id": 1, "season": 2026},
        "games": {
            "played": {"all": 10, "home": 5, "away": 5},
            "wins": {
                "all": {"total": 6, "percentage": ".600"},
                "home": {"total": 4, "percentage": ".800"},
                "away": {"total": 2, "percentage": ".400"},
            },
            "loses": {
                "all": {"total": 4, "percentage": ".400"},
                "home": {"total": 1, "percentage": ".200"},
                "away": {"total": 3, "percentage": ".600"},
            },
        },
        "points": {
            "for": {
                "total": {"all": 50, "home": 30, "away": 20},
                "average": {"all": 5.0, "home": 6.0, "away": 4.0},
            },
            "against": {
                "total": {"all": 40, "home": 15, "away": 25},
                "average": {"all": 4.0, "home": 3.0, "away": 5.0},
            },
        },
    }


class FakeClient:
    def __init__(self):
        self.request_count = 0
        self.remaining_budget = 99
        self.calls = []

    def standings_with_receipt(self, league_id, season):
        self.request_count += 1
        self.remaining_budget -= 1
        self.calls.append(("standings", league_id, season))
        rows = []
        for team_id in (10, 20, 30):
            rows.append(
                {
                    "position": 1,
                    "stage": "Regular Season",
                    "group": {"name": "MLB"},
                    "games": {
                        "played": 10,
                        "win": {"total": 6, "percentage": ".600"},
                        "lose": {"total": 4, "percentage": ".400"},
                    },
                    "points": {"for": 50, "against": 40},
                    "team": {"id": team_id, "name": f"Team {team_id}"},
                }
            )
        return rows, _receipt("standings")

    def team_statistics_with_receipt(self, team_id, league_id, season):
        self.request_count += 1
        self.remaining_budget -= 1
        self.calls.append(("team_stats", team_id, league_id, season))
        return _team_stats(team_id), _receipt(f"team{team_id}")

    def bet_types_with_receipt(self):
        self.request_count += 1
        self.remaining_budget -= 1
        self.calls.append(("bets",))
        return [{"id": 1, "name": "Home/Away"}], _receipt("bets")

    def bookmakers_with_receipt(self):
        self.request_count += 1
        self.remaining_budget -= 1
        self.calls.append(("books",))
        return [{"id": 1, "name": "1xbet"}], _receipt("books")


class FakeRepository:
    def __init__(self):
        self.standings_time = None
        self.team_ids = ()
        self.team_times = {}
        self.catalog_times = {}
        self.standings = []
        self.team_stats = []
        self.catalogs = []

    def latest_standings_observed_at(self, *, league_id, season):
        return self.standings_time

    def latest_standing_team_ids(self, *, league_id, season):
        return self.team_ids

    def latest_team_statistics_times(self, *, league_id, season):
        return dict(self.team_times)

    def latest_catalog_observed_at(self, catalog_type):
        return self.catalog_times.get(catalog_type)

    def append_standings(self, records):
        records = tuple(records)
        self.standings.extend(records)
        if records:
            self.standings_time = datetime.fromisoformat(records[0].observed_at)
            self.team_ids = tuple(record.team_id for record in records)
        return len(records)

    def append_team_statistics(self, record):
        self.team_stats.append(record)
        self.team_times[record.team_id] = datetime.fromisoformat(record.observed_at)
        return True

    def append_catalog(self, record):
        self.catalogs.append(record)
        self.catalog_times[record.catalog_type] = datetime.fromisoformat(
            record.observed_at
        )
        return True


def test_slow_collection_never_exceeds_leftover_request_cap() -> None:
    client = FakeClient()
    repository = FakeRepository()

    result = collect_slow_provider_data(
        client,
        repository,
        now=datetime(2026, 9, 26, 8, 0, tzinfo=UTC),
        max_requests=3,
    )

    assert result["requests"] == 3
    assert result["standings_calls"] == 1
    assert result["team_statistics_calls"] == 2
    assert result["team_statistics_due_uncollected"] == 1
    assert result["catalog_calls"] == 0
    assert client.calls == [
        ("standings", 1, 2026),
        ("team_stats", 10, 1, 2026),
        ("team_stats", 20, 1, 2026),
    ]


def test_slow_sources_are_not_repolled_before_cadence() -> None:
    client = FakeClient()
    repository = FakeRepository()
    now = datetime(2026, 9, 26, 8, 0, tzinfo=UTC)

    rows, receipt = client.standings_with_receipt(1, 2026)
    records = canonical_standings(rows, receipt, league_id=1, season=2026)
    repository.append_standings(records)
    for team_id in repository.team_ids:
        payload, receipt = client.team_statistics_with_receipt(team_id, 1, 2026)
        from quantbot.baseball.provider_data import canonical_team_statistics

        repository.append_team_statistics(canonical_team_statistics(payload, receipt))
    repository.catalog_times = {
        "BET_TYPES": now - timedelta(days=1),
        "BOOKMAKERS": now - timedelta(days=1),
    }

    client.calls.clear()
    client.request_count = 0
    client.remaining_budget = 99

    result = collect_slow_provider_data(
        client,
        repository,
        now=now + timedelta(hours=1),
        max_requests=10,
    )

    assert result["requests"] == 0
    assert client.calls == []


def test_catalogs_use_weekly_cadence_after_team_data_priority() -> None:
    client = FakeClient()
    repository = FakeRepository()
    now = datetime(2026, 9, 26, 8, 0, tzinfo=UTC)
    repository.standings_time = now
    repository.team_ids = ()
    repository.catalog_times = {
        "BET_TYPES": now - timedelta(days=8),
        "BOOKMAKERS": now - timedelta(days=8),
    }

    result = collect_slow_provider_data(
        client,
        repository,
        now=now,
        max_requests=2,
    )

    assert result["catalog_calls"] == 2
    assert result["catalogs_inserted"] == 2
    assert client.calls == [("bets",), ("books",)]
