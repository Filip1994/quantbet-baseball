from datetime import UTC, datetime

from quantbot.baseball.fixture_evidence import FixtureObservation
from quantbot.baseball.mlb_identity_bootstrap import collect_mlb_identity_bootstrap
from quantbot.baseball.raw_archive import ArchiveReceipt


def _fixture():
    return FixtureObservation(
        fixture_observation_id="33333333-3333-4333-8333-333333333333",
        game_id="186584",
        provider="api-sports-baseball",
        provider_game_id=186584,
        league="MLB",
        home_team_id=2001,
        home_team_name="New York Mets",
        away_team_id=2002,
        away_team_name="Philadelphia Phillies",
        kickoff_at="2026-09-26T23:10:00+00:00",
        provider_status="NS",
        observed_at="2026-09-26T16:00:00+00:00",
        source_payload_ref="s3://raw/api-sports/games.json",
        source_payload_checksum="a" * 64,
        schema_version="1.0",
    )


def _schedule():
    return {
        "dates": [
            {
                "date": "2026-09-26",
                "games": [
                    {
                        "gamePk": 900001,
                        "gameDate": "2026-09-26T23:12:00Z",
                        "teams": {
                            "home": {"team": {"id": 121, "name": "New York Mets"}},
                            "away": {
                                "team": {
                                    "id": 143,
                                    "name": "Philadelphia Phillies",
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
        assert date_iso == "2026-09-26"
        self.calls += 1
        return (
            _schedule(),
            ArchiveReceipt(
                ref="s3://raw/official-mlb/schedule.json",
                checksum="b" * 64,
                captured_at=(
                    captured_at or datetime(2026, 9, 26, 16, 30, tzinfo=UTC)
                ).isoformat(),
            ),
        )


class FakeRepository:
    def __init__(self):
        self.fixtures = (_fixture(),)
        self.mappings = {}
        self.links = {}

    def latest_mlb_fixtures_for_schedule_date(
        self,
        *,
        date_iso,
        observed_by,
    ):
        assert date_iso == "2026-09-26"
        assert observed_by.tzinfo is not None
        return self.fixtures

    def team_mappings(self, mapping_version):
        return tuple(
            value
            for (version, _), value in sorted(self.mappings.items())
            if version == mapping_version
        )

    def append_team_mapping(self, record):
        key = (record.mapping_version, record.api_sports_team_id)
        if key in self.mappings:
            return False
        self.mappings[key] = record
        return True

    def game_link_for_provider_game(self, *, mapping_version, provider_game_id):
        return self.links.get((mapping_version, provider_game_id))

    def append_game_link(self, record):
        key = (record.mapping_version, record.api_sports_provider_game_id)
        if key in self.links:
            return False
        self.links[key] = record
        return True


def test_identity_bootstrap_is_bounded_and_idempotent() -> None:
    client = FakeClient()
    repository = FakeRepository()
    now = datetime(2026, 9, 26, 16, 30, tzinfo=UTC)

    first = collect_mlb_identity_bootstrap(
        client,
        repository,
        date_iso="2026-09-26",
        mapping_version="mlb-2026-v1",
        now=now,
        expected_team_count=2,
    )

    assert first["status"] == "COMPLETE"
    assert first["schedule_calls"] == 1
    assert first["fixtures_seen"] == 1
    assert first["team_mappings_inserted"] == 2
    assert first["team_mappings_total"] == 2
    assert first["game_links_inserted"] == 1
    assert first["game_links_total_for_target"] == 1
    assert first["mapping_failures"] == 0
    assert first["link_failures"] == 0
    assert first["ready_for_enrichment"] == 1
    assert client.calls == 1

    second = collect_mlb_identity_bootstrap(
        client,
        repository,
        date_iso="2026-09-26",
        mapping_version="mlb-2026-v1",
        now=now,
        expected_team_count=2,
    )

    assert second["status"] == "ALREADY_DONE"
    assert second["schedule_calls"] == 0
    assert second["fixtures_already_linked"] == 1
    assert second["ready_for_enrichment"] == 1
    assert client.calls == 1


def test_identity_bootstrap_fails_closed_on_ambiguous_schedule() -> None:
    class AmbiguousClient(FakeClient):
        def schedule_identity_map_with_receipt(self, date_iso, *, captured_at=None):
            payload, receipt = super().schedule_identity_map_with_receipt(
                date_iso,
                captured_at=captured_at,
            )
            duplicate = dict(payload["dates"][0]["games"][0])
            duplicate["gamePk"] = 900002
            payload["dates"][0]["games"].append(duplicate)
            return payload, receipt

    client = AmbiguousClient()
    repository = FakeRepository()

    result = collect_mlb_identity_bootstrap(
        client,
        repository,
        date_iso="2026-09-26",
        mapping_version="mlb-2026-v1",
        now=datetime(2026, 9, 26, 16, 30, tzinfo=UTC),
        expected_team_count=2,
    )

    assert result["status"] == "FAILED"
    assert result["schedule_calls"] == 1
    assert result["mapping_failures"] == 1
    assert result["team_mappings_total"] == 0
    assert result["game_links_inserted"] == 0
    assert result["ready_for_enrichment"] == 0
    assert repository.mappings == {}
    assert repository.links == {}
