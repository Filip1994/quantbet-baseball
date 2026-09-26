from datetime import UTC, datetime
from types import SimpleNamespace

from quantbot.baseball.fixture_evidence import FixtureObservation
from quantbot.baseball.mlb_identity_diagnostic import diagnose_mlb_identity_coverage


def _fixture(
    provider_game_id: int,
    *,
    home_id: int,
    home_name: str,
    away_id: int,
    away_name: str,
) -> FixtureObservation:
    return FixtureObservation(
        fixture_observation_id=f"00000000-0000-4000-8000-{provider_game_id:012d}",
        game_id=str(provider_game_id),
        provider="api-sports-baseball",
        provider_game_id=provider_game_id,
        league="MLB",
        home_team_id=home_id,
        home_team_name=home_name,
        away_team_id=away_id,
        away_team_name=away_name,
        kickoff_at="2026-09-26T23:10:00+00:00",
        provider_status="NS",
        observed_at="2026-09-26T17:00:00+00:00",
        source_payload_ref="s3://raw/api-sports/games.json",
        source_payload_checksum="a" * 64,
        schema_version="1.0",
    )


class FakeRepository:
    def __init__(self) -> None:
        self.fixtures = (
            _fixture(
                1001,
                home_id=1,
                home_name="Mapped Home",
                away_id=2,
                away_name="Mapped Away",
            ),
            _fixture(
                1002,
                home_id=3,
                home_name="Mapped Team",
                away_id=4,
                away_name="Missing Team",
            ),
        )
        self.mappings = (
            SimpleNamespace(api_sports_team_id=1),
            SimpleNamespace(api_sports_team_id=2),
            SimpleNamespace(api_sports_team_id=3),
        )

    def latest_mlb_fixtures_for_schedule_date(self, *, date_iso, observed_by):
        assert date_iso == "2026-09-26"
        assert observed_by.tzinfo is not None
        return self.fixtures

    def team_mappings(self, mapping_version):
        assert mapping_version == "mlb-2026-v1"
        return self.mappings

    def game_link_for_provider_game(self, *, mapping_version, provider_game_id):
        assert mapping_version == "mlb-2026-v1"
        if provider_game_id == 1001:
            return SimpleNamespace(api_sports_provider_game_id=1001)
        return None


def test_identity_diagnostic_is_read_only_coverage_evidence() -> None:
    result = diagnose_mlb_identity_coverage(
        FakeRepository(),
        date_iso="2026-09-26",
        mapping_version="mlb-2026-v1",
        observed_by=datetime(2026, 9, 26, 17, 30, tzinfo=UTC),
    )

    assert result["status"] == "INCOMPLETE"
    assert result["provider_calls"] == 0
    assert result["fixtures_seen"] == 2
    assert result["team_mappings_total"] == 3
    assert result["game_links_total_for_target"] == 1
    assert result["unresolved_fixtures_count"] == 1
    assert result["unresolved_fixtures"] == [
        {
            "provider_game_id": 1002,
            "kickoff_at": "2026-09-26T23:10:00+00:00",
            "provider_status": "NS",
            "observed_at": "2026-09-26T17:00:00+00:00",
            "home_team_id": 3,
            "home_team_name": "Mapped Team",
            "away_team_id": 4,
            "away_team_name": "Missing Team",
            "source_payload_ref": "s3://raw/api-sports/games.json",
            "source_payload_checksum": "a" * 64,
            "link_present": False,
            "missing_team_mappings": [
                {
                    "side": "away",
                    "api_sports_team_id": 4,
                    "api_sports_team_name": "Missing Team",
                }
            ],
            "reason_code": "MISSING_TEAM_MAPPING",
        }
    ]
