from datetime import UTC, datetime
from types import SimpleNamespace

from quantbot.baseball.official_mlb_live_enrichment import (
    collect_live_pregame_components,
)
from quantbot.baseball.raw_archive import ArchiveReceipt


def _payload(*, home_team_id=121):
    return {
        "gamePk": 900001,
        "metaData": {"timeStamp": "20260927_162900"},
        "gameData": {
            "datetime": {"dateTime": "2026-09-27T18:00:00Z"},
            "status": {
                "abstractGameState": "Preview",
                "detailedState": "Pre-Game",
            },
            "teams": {
                "away": {"id": 143, "name": "Philadelphia Phillies"},
                "home": {"id": home_team_id, "name": "New York Mets"},
            },
            "probablePitchers": {
                "away": {"id": 650911, "fullName": "Away Starter"},
                "home": {"id": 804636, "fullName": "Home Starter"},
            },
            "venue": {
                "id": 3289,
                "name": "Citi Field",
                "fieldInfo": {
                    "roofType": "Open",
                    "turfType": "Grass",
                },
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


def _link(*, first_pitch="2026-09-27T18:00:00+00:00"):
    return SimpleNamespace(
        api_sports_provider_game_id=186584,
        mlb_game_pk=900001,
        mlb_home_team_id=121,
        mlb_away_team_id=143,
        official_mlb_first_pitch=first_pitch,
    )


class FakeClient:
    def __init__(self, *, home_team_id=121):
        self.calls = 0
        self.home_team_id = home_team_id

    def game_feed_with_receipt(self, game_pk, *, timecode=None, captured_at=None):
        assert game_pk == 900001
        assert timecode is None
        self.calls += 1
        return (
            _payload(home_team_id=self.home_team_id),
            ArchiveReceipt(
                ref="s3://raw/official-mlb/live-feed.json",
                checksum="a" * 64,
                captured_at=(
                    captured_at or datetime(2026, 9, 27, 16, 30, tzinfo=UTC)
                ).isoformat(),
            ),
        )


class FakeIdentityRepository:
    def __init__(self, links=None):
        self.links = tuple(links or (_link(),))

    def game_links(self, mapping_version):
        assert mapping_version == "mlb-2026-v1"
        return self.links


class FakeComponentRepository:
    def __init__(self):
        self.rows = []

    def latest_components_for_game(self, *, mlb_game_pk, as_of):
        assert as_of.tzinfo is not None
        return tuple(
            row
            for row in self.rows
            if row.mlb_game_pk == mlb_game_pk
            and datetime.fromisoformat(row.source_observed_at) <= as_of
        )

    def append_components(self, records):
        self.rows.extend(records)
        return len(records)


def test_live_enrichment_is_bounded_and_zero_repeat() -> None:
    client = FakeClient()
    identity = FakeIdentityRepository()
    components = FakeComponentRepository()
    now = datetime(2026, 9, 27, 16, 30, tzinfo=UTC)

    first = collect_live_pregame_components(
        client,
        identity,
        components,
        mapping_version="mlb-2026-v1",
        now=now,
        horizon_minutes=150,
        max_calls=1,
    )

    assert first["status"] == "COMPLETE"
    assert first["due_games"] == 1
    assert first["provider_calls"] == 1
    assert first["games_completed"] == 1
    assert first["components_inserted"] == 7
    assert first["ready_for_feature_snapshot"] == 1
    assert client.calls == 1

    second = collect_live_pregame_components(
        client,
        identity,
        components,
        mapping_version="mlb-2026-v1",
        now=now,
        horizon_minutes=150,
        max_calls=1,
    )

    assert second["status"] == "COMPLETE"
    assert second["already_captured"] == 1
    assert second["provider_calls"] == 0
    assert second["components_inserted"] == 0
    assert second["ready_for_feature_snapshot"] == 1
    assert client.calls == 1


def test_live_enrichment_does_not_call_outside_horizon() -> None:
    client = FakeClient()
    identity = FakeIdentityRepository(
        links=(_link(first_pitch="2026-09-27T20:00:00+00:00"),)
    )
    components = FakeComponentRepository()

    result = collect_live_pregame_components(
        client,
        identity,
        components,
        mapping_version="mlb-2026-v1",
        now=datetime(2026, 9, 27, 16, 30, tzinfo=UTC),
        horizon_minutes=150,
        max_calls=1,
    )

    assert result["status"] == "NO_DUE_GAMES"
    assert result["provider_calls"] == 0
    assert client.calls == 0


def test_live_enrichment_fails_before_insert_on_identity_mismatch() -> None:
    client = FakeClient(home_team_id=999)
    components = FakeComponentRepository()

    result = collect_live_pregame_components(
        client,
        FakeIdentityRepository(),
        components,
        mapping_version="mlb-2026-v1",
        now=datetime(2026, 9, 27, 16, 30, tzinfo=UTC),
        horizon_minutes=150,
        max_calls=1,
    )

    assert result["status"] == "PARTIAL"
    assert result["provider_calls"] == 1
    assert result["games_completed"] == 0
    assert result["components_inserted"] == 0
    assert components.rows == []
