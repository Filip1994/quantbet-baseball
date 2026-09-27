from datetime import UTC, datetime
from types import SimpleNamespace

from quantbot.baseball.official_mlb_enrichment_canary import (
    run_enrichment_canary_with_dependencies,
)
from quantbot.baseball.raw_archive import ArchiveReceipt


def _payload(*, home_team_id=121):
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
                "home": {"id": home_team_id, "name": "New York Mets"},
            },
            "probablePitchers": {
                "away": {"id": 650911, "fullName": "Cristopher Sánchez"},
                "home": {"id": 804636, "fullName": "Jonah Tong"},
            },
            "venue": {
                "id": 3289,
                "name": "Citi Field",
                "fieldInfo": {"roofType": "Open", "turfType": "Grass"},
                "location": {
                    "elevation": 10,
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
                        "bullpen": [201, 202],
                    },
                    "home": {
                        "battingOrder": list(range(301, 310)),
                        "bullpen": [401, 402],
                    },
                }
            }
        },
    }


class FakeClient:
    def __init__(self, *, home_team_id=121):
        self.calls = 0
        self.home_team_id = home_team_id

    def game_feed_with_receipt(self, game_pk, *, timecode=None, captured_at=None):
        assert game_pk == 823570
        assert timecode == "20260920_151000"
        self.calls += 1
        return (
            _payload(home_team_id=self.home_team_id),
            ArchiveReceipt(
                ref="s3://raw/official-mlb/feed.json",
                checksum="a" * 64,
                captured_at=(
                    captured_at or datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
                ).isoformat(),
            ),
        )


class FakeIdentityRepository:
    def team_mappings(self, mapping_version):
        assert mapping_version == "mlb-2026-v1"
        return (SimpleNamespace(), SimpleNamespace())

    def game_links(self, mapping_version):
        assert mapping_version == "mlb-2026-v1"
        return (
            SimpleNamespace(
                api_sports_provider_game_id=186584,
                mlb_game_pk=823570,
                mlb_home_team_id=121,
                mlb_away_team_id=143,
                official_mlb_first_pitch="2026-09-20T17:10:00+00:00",
            ),
        )


class FakeComponentRepository:
    def __init__(self):
        self.rows = []

    def components_for_requested_timecode(self, *, mlb_game_pk, requested_timecode):
        return tuple(
            row
            for row in self.rows
            if row.mlb_game_pk == mlb_game_pk
            and row.requested_timecode == requested_timecode
        )

    def append_components(self, records):
        assert not self.rows
        self.rows.extend(records)
        return len(records)


def test_enrichment_canary_is_bounded_and_zero_repeat() -> None:
    client = FakeClient()
    identity = FakeIdentityRepository()
    components = FakeComponentRepository()
    now = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)

    first = run_enrichment_canary_with_dependencies(
        client,
        identity,
        components,
        mapping_version="mlb-2026-v1",
        now=now,
        expected_team_count=2,
    )

    assert first["status"] == "COMPLETE"
    assert first["provider_calls"] == 1
    assert first["components_inserted"] == 7
    assert first["components_total"] == 7
    assert first["point_in_time_eligible"] == 1
    assert first["requested_timecode"] == "20260920_151000"
    assert first["source_observed_at"] == "2026-09-20T15:12:58+00:00"
    assert client.calls == 1

    second = run_enrichment_canary_with_dependencies(
        client,
        identity,
        components,
        mapping_version="mlb-2026-v1",
        now=now,
        expected_team_count=2,
    )

    assert second["status"] == "ALREADY_DONE"
    assert second["provider_calls"] == 0
    assert second["components_total"] == 7
    assert second["point_in_time_eligible"] == 1
    assert client.calls == 1


def test_enrichment_canary_fails_before_insert_on_game_identity_mismatch() -> None:
    client = FakeClient(home_team_id=999)
    components = FakeComponentRepository()

    result = run_enrichment_canary_with_dependencies(
        client,
        FakeIdentityRepository(),
        components,
        mapping_version="mlb-2026-v1",
        now=datetime(2026, 9, 27, 12, 0, tzinfo=UTC),
        expected_team_count=2,
    )

    assert result["status"] == "FAILED"
    assert result["reason_codes"] == ["GAME_IDENTITY_MISMATCH"]
    assert result["provider_calls"] == 1
    assert components.rows == []


def test_enrichment_canary_blocks_partial_existing_component_set_without_call() -> None:
    client = FakeClient()
    complete_repo = FakeComponentRepository()
    first = run_enrichment_canary_with_dependencies(
        client,
        FakeIdentityRepository(),
        complete_repo,
        mapping_version="mlb-2026-v1",
        now=datetime(2026, 9, 27, 12, 0, tzinfo=UTC),
        expected_team_count=2,
    )
    assert first["status"] == "COMPLETE"

    partial_repo = FakeComponentRepository()
    partial_repo.rows.append(complete_repo.rows[0])
    before_calls = client.calls

    result = run_enrichment_canary_with_dependencies(
        client,
        FakeIdentityRepository(),
        partial_repo,
        mapping_version="mlb-2026-v1",
        now=datetime(2026, 9, 27, 12, 1, tzinfo=UTC),
        expected_team_count=2,
    )

    assert result["status"] == "BLOCKED"
    assert result["reason_codes"] == ["PARTIAL_EXISTING_COMPONENT_SET"]
    assert result["provider_calls"] == 0
    assert client.calls == before_calls
