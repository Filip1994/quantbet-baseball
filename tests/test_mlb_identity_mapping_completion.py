from datetime import UTC, datetime

from quantbot.baseball.fixture_evidence import FixtureObservation
from quantbot.baseball.mlb_identity_mapping_completion import (
    complete_mlb_team_mappings,
)
from quantbot.baseball.raw_archive import ArchiveReceipt


def _fixture():
    return FixtureObservation(
        fixture_observation_id="66666666-6666-4666-8666-666666666666",
        game_id="200001",
        provider="api-sports-baseball",
        provider_game_id=200001,
        league="MLB",
        home_team_id=4,
        home_team_name="Baltimore Orioles",
        away_team_id=25,
        away_team_name="New York Yankees",
        kickoff_at="2026-09-27T17:05:00+00:00",
        provider_status="NS",
        observed_at="2026-09-26T23:16:00+00:00",
        source_payload_ref="s3://raw/api-sports/games-2026-09-27.json",
        source_payload_checksum="a" * 64,
        schema_version="1.0",
    )


def _schedule():
    return {
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
                                    "id": 110,
                                    "name": "Baltimore Orioles",
                                }
                            },
                            "away": {
                                "team": {
                                    "id": 147,
                                    "name": "New York Yankees",
                                }
                            },
                        },
                    }
                ],
            }
        ]
    }


class FakeClient:
    def __init__(self):
        self.calls = 0

    def schedule_identity_map_with_receipt(self, date_iso, *, captured_at=None):
        assert date_iso == "2026-09-27"
        self.calls += 1
        return (
            _schedule(),
            ArchiveReceipt(
                ref="s3://raw/official-mlb/schedule-2026-09-27.json",
                checksum="b" * 64,
                captured_at=(
                    captured_at or datetime(2026, 9, 26, 23, 20, tzinfo=UTC)
                ).isoformat(),
            ),
        )


class FakeRepository:
    def __init__(self):
        self.fixtures = (_fixture(),)
        self.mappings = {}

    def latest_mlb_fixtures_for_provider_query_date(
        self,
        *,
        date_iso,
        observed_by,
    ):
        assert date_iso == "2026-09-27"
        assert observed_by.tzinfo is not None
        return self.fixtures

    def team_mappings(self, mapping_version):
        return tuple(
            value
            for (version, _), value in sorted(self.mappings.items())
            if version == mapping_version
        )

    def append_team_mappings_atomically(self, records):
        for record in records:
            key = (record.mapping_version, record.api_sports_team_id)
            assert key not in self.mappings
        for record in records:
            self.mappings[(record.mapping_version, record.api_sports_team_id)] = record
        return len(records)


def test_mapping_completion_is_bounded_atomic_and_idempotent() -> None:
    client = FakeClient()
    repository = FakeRepository()
    now = datetime(2026, 9, 26, 23, 20, tzinfo=UTC)

    first = complete_mlb_team_mappings(
        client,
        repository,
        date_iso="2026-09-27",
        mapping_version="mlb-2026-v1",
        now=now,
        expected_team_count=2,
    )

    assert first["status"] == "COMPLETE"
    assert first["schedule_calls"] == 1
    assert first["fixtures_seen"] == 1
    assert first["candidate_fixtures"] == 1
    assert first["unmapped_team_ids_seen"] == [4, 25]
    assert first["team_mappings_inserted"] == 2
    assert first["team_mappings_total"] == 2
    assert first["mapping_failures"] == 0
    assert first["ready_for_enrichment"] == 1
    assert client.calls == 1

    second = complete_mlb_team_mappings(
        client,
        repository,
        date_iso="2026-09-27",
        mapping_version="mlb-2026-v1",
        now=now,
        expected_team_count=2,
    )

    assert second["status"] == "ALREADY_DONE"
    assert second["schedule_calls"] == 0
    assert second["team_mappings_inserted"] == 0
    assert second["ready_for_enrichment"] == 1
    assert client.calls == 1


def test_mapping_completion_accepts_unique_exact_pair_after_start_time_change() -> None:
    class ShiftedRepository(FakeRepository):
        def __init__(self):
            super().__init__()
            self.fixtures = (
                FixtureObservation(
                    fixture_observation_id="77777777-7777-4777-8777-777777777777",
                    game_id="187589",
                    provider="api-sports-baseball",
                    provider_game_id=187589,
                    league="MLB",
                    home_team_id=25,
                    home_team_name="New York Yankees",
                    away_team_id=4,
                    away_team_name="Baltimore Orioles",
                    kickoff_at="2026-09-27T19:20:00+00:00",
                    provider_status="NS",
                    observed_at="2026-09-26T23:30:00+00:00",
                    source_payload_ref="s3://raw/api-sports/games-2026-09-27.json",
                    source_payload_checksum="c" * 64,
                    schema_version="1.0",
                ),
            )

    class ShiftedClient(FakeClient):
        def schedule_identity_map_with_receipt(self, date_iso, *, captured_at=None):
            self.calls += 1
            return (
                {
                    "dates": [
                        {
                            "date": "2026-09-27",
                            "games": [
                                {
                                    "gamePk": 900020,
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
                                }
                            ],
                        }
                    ]
                },
                ArchiveReceipt(
                    ref="s3://raw/official-mlb/schedule-shifted.json",
                    checksum="d" * 64,
                    captured_at=(
                        captured_at
                        or datetime(2026, 9, 26, 23, 30, tzinfo=UTC)
                    ).isoformat(),
                ),
            )

    client = ShiftedClient()
    repository = ShiftedRepository()

    result = complete_mlb_team_mappings(
        client,
        repository,
        date_iso="2026-09-27",
        mapping_version="mlb-2026-v1",
        now=datetime(2026, 9, 26, 23, 30, tzinfo=UTC),
        expected_team_count=2,
    )

    assert result["status"] == "COMPLETE"
    assert result["mapping_failures"] == 0
    assert result["schedule_time_shift_matches"] == 1
    assert result["schedule_time_shift_provider_game_ids"] == [187589]
    assert result["team_mappings_inserted"] == 2
    assert result["team_mappings_total"] == 2


def test_mapping_completion_rejects_ambiguous_exact_pair_after_time_change() -> None:
    class ShiftedRepository(FakeRepository):
        def __init__(self):
            super().__init__()
            self.fixtures = (
                FixtureObservation(
                    fixture_observation_id="88888888-8888-4888-8888-888888888888",
                    game_id="187589",
                    provider="api-sports-baseball",
                    provider_game_id=187589,
                    league="MLB",
                    home_team_id=25,
                    home_team_name="New York Yankees",
                    away_team_id=4,
                    away_team_name="Baltimore Orioles",
                    kickoff_at="2026-09-27T19:20:00+00:00",
                    provider_status="NS",
                    observed_at="2026-09-26T23:30:00+00:00",
                    source_payload_ref="s3://raw/api-sports/games-2026-09-27.json",
                    source_payload_checksum="e" * 64,
                    schema_version="1.0",
                ),
            )

    class AmbiguousShiftClient(FakeClient):
        def schedule_identity_map_with_receipt(self, date_iso, *, captured_at=None):
            self.calls += 1
            game = {
                "gamePk": 900030,
                "gameDate": "2026-09-27T17:05:00Z",
                "teams": {
                    "home": {"team": {"id": 147, "name": "New York Yankees"}},
                    "away": {"team": {"id": 110, "name": "Baltimore Orioles"}},
                },
            }
            duplicate = {
                **game,
                "gamePk": 900031,
                "gameDate": "2026-09-27T17:35:00Z",
            }
            return (
                {"dates": [{"date": "2026-09-27", "games": [game, duplicate]}]},
                ArchiveReceipt(
                    ref="s3://raw/official-mlb/schedule-ambiguous.json",
                    checksum="f" * 64,
                    captured_at=(
                        captured_at
                        or datetime(2026, 9, 26, 23, 30, tzinfo=UTC)
                    ).isoformat(),
                ),
            )

    client = AmbiguousShiftClient()
    repository = ShiftedRepository()

    result = complete_mlb_team_mappings(
        client,
        repository,
        date_iso="2026-09-27",
        mapping_version="mlb-2026-v1",
        now=datetime(2026, 9, 26, 23, 30, tzinfo=UTC),
        expected_team_count=2,
    )

    assert result["status"] == "FAILED"
    assert result["mapping_failures"] == 1
    assert result["schedule_time_shift_matches"] == 0
    assert result["team_mappings_inserted"] == 0
    assert repository.mappings == {}


def test_mapping_completion_fails_closed_before_any_insert() -> None:
    class AmbiguousClient(FakeClient):
        def schedule_identity_map_with_receipt(self, date_iso, *, captured_at=None):
            payload, receipt = super().schedule_identity_map_with_receipt(
                date_iso,
                captured_at=captured_at,
            )
            duplicate = dict(payload["dates"][0]["games"][0])
            duplicate["gamePk"] = 900011
            payload["dates"][0]["games"].append(duplicate)
            return payload, receipt

    client = AmbiguousClient()
    repository = FakeRepository()

    result = complete_mlb_team_mappings(
        client,
        repository,
        date_iso="2026-09-27",
        mapping_version="mlb-2026-v1",
        now=datetime(2026, 9, 26, 23, 20, tzinfo=UTC),
        expected_team_count=2,
    )

    assert result["status"] == "FAILED"
    assert result["schedule_calls"] == 1
    assert result["mapping_failures"] == 1
    assert result["team_mappings_inserted"] == 0
    assert repository.mappings == {}
