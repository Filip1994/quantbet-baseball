from datetime import UTC, datetime

from quantbot.baseball.fixture_evidence import FixtureObservation
from quantbot.baseball.mlb_game_linking import collect_mlb_game_links
from quantbot.baseball.mlb_identity import MLBTeamIdentityMapping
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
        kickoff_at="2026-09-27T23:10:00+00:00",
        provider_status="NS",
        observed_at="2026-09-27T16:00:00+00:00",
        source_payload_ref="s3://raw/api-sports/games.json",
        source_payload_checksum="a" * 64,
        schema_version="1.0",
    )


def _mapping(*, api_id, api_name, mlb_id, mlb_name):
    return MLBTeamIdentityMapping(
        mapping_id=f"mapping-{api_id}",
        mapping_version="mlb-2026-v1",
        api_sports_team_id=api_id,
        api_sports_team_name=api_name,
        official_mlb_team_id=mlb_id,
        official_mlb_team_name=mlb_name,
        verified_at="2026-09-26T16:30:00+00:00",
        api_fixture_observation_id="33333333-3333-4333-8333-333333333333",
        api_source_payload_ref="s3://raw/api-sports/games.json",
        api_source_payload_checksum="a" * 64,
        mlb_schedule_source_payload_ref="s3://raw/official-mlb/schedule.json",
        mlb_schedule_source_payload_checksum="b" * 64,
    )


def _schedule():
    return {
        "dates": [
            {
                "date": "2026-09-27",
                "games": [
                    {
                        "gamePk": 900001,
                        "gameDate": "2026-09-27T23:12:00Z",
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
    def __init__(self, payload=None):
        self.calls = 0
        self.payload = payload or _schedule()

    def schedule_identity_map_with_receipt(self, date_iso, *, captured_at=None):
        assert date_iso == "2026-09-27"
        self.calls += 1
        return (
            self.payload,
            ArchiveReceipt(
                ref="s3://raw/official-mlb/schedule.json",
                checksum="c" * 64,
                captured_at=(
                    captured_at or datetime(2026, 9, 27, 16, 30, tzinfo=UTC)
                ).isoformat(),
            ),
        )


class FakeRepository:
    def __init__(self, *, complete_registry=True):
        self.fixtures = (_fixture(),)
        self.mappings = [
            _mapping(
                api_id=2001,
                api_name="New York Mets",
                mlb_id=121,
                mlb_name="New York Mets",
            )
        ]
        if complete_registry:
            self.mappings.append(
                _mapping(
                    api_id=2002,
                    api_name="Philadelphia Phillies",
                    mlb_id=143,
                    mlb_name="Philadelphia Phillies",
                )
            )
        self.links = {}

    def latest_mlb_fixtures_for_schedule_date(self, *, date_iso, observed_by):
        assert date_iso == "2026-09-27"
        assert observed_by.tzinfo is not None
        return self.fixtures

    def team_mappings(self, mapping_version):
        assert mapping_version == "mlb-2026-v1"
        return tuple(self.mappings)

    def game_link_for_provider_game(self, *, mapping_version, provider_game_id):
        return self.links.get((mapping_version, provider_game_id))

    def append_game_link(self, record):
        key = (record.mapping_version, record.api_sports_provider_game_id)
        if key in self.links:
            return False
        self.links[key] = record
        return True


def test_game_linking_uses_completed_registry_and_zero_repeats() -> None:
    client = FakeClient()
    repository = FakeRepository()
    now = datetime(2026, 9, 27, 16, 30, tzinfo=UTC)

    first = collect_mlb_game_links(
        client,
        repository,
        date_iso="2026-09-27",
        mapping_version="mlb-2026-v1",
        now=now,
        expected_team_count=2,
    )

    assert first["status"] == "COMPLETE"
    assert first["schedule_calls"] == 1
    assert first["team_mappings_total"] == 2
    assert first["game_links_inserted"] == 1
    assert first["game_links_total_for_target"] == 1
    assert first["ready_for_enrichment"] == 1
    assert client.calls == 1

    second = collect_mlb_game_links(
        client,
        repository,
        date_iso="2026-09-27",
        mapping_version="mlb-2026-v1",
        now=now,
        expected_team_count=2,
    )

    assert second["status"] == "ALREADY_DONE"
    assert second["schedule_calls"] == 0
    assert second["game_links_inserted"] == 0
    assert second["ready_for_enrichment"] == 1
    assert client.calls == 1


def test_game_linking_blocks_before_provider_call_when_registry_incomplete() -> None:
    client = FakeClient()
    repository = FakeRepository(complete_registry=False)

    result = collect_mlb_game_links(
        client,
        repository,
        date_iso="2026-09-27",
        mapping_version="mlb-2026-v1",
        now=datetime(2026, 9, 27, 16, 30, tzinfo=UTC),
        expected_team_count=2,
    )

    assert result["status"] == "TEAM_REGISTRY_INCOMPLETE"
    assert result["schedule_calls"] == 0
    assert result["game_links_inserted"] == 0
    assert client.calls == 0


def test_game_linking_fails_closed_on_ambiguous_official_schedule() -> None:
    payload = _schedule()
    duplicate = dict(payload["dates"][0]["games"][0])
    duplicate["gamePk"] = 900002
    payload["dates"][0]["games"].append(duplicate)
    client = FakeClient(payload)
    repository = FakeRepository()

    result = collect_mlb_game_links(
        client,
        repository,
        date_iso="2026-09-27",
        mapping_version="mlb-2026-v1",
        now=datetime(2026, 9, 27, 16, 30, tzinfo=UTC),
        expected_team_count=2,
    )

    assert result["status"] == "PARTIAL"
    assert result["schedule_calls"] == 1
    assert result["link_failures"] == 1
    assert result["game_links_inserted"] == 0
    assert result["ready_for_enrichment"] == 0
