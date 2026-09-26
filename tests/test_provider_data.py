from quantbot.baseball.provider_data import (
    canonical_reference_catalog,
    canonical_standings,
    canonical_team_statistics,
)
from quantbot.baseball.raw_archive import ArchiveReceipt


def _receipt(checksum="a" * 64):
    return ArchiveReceipt(
        ref="s3://raw/provider.json",
        checksum=checksum,
        captured_at="2026-09-26T08:00:00+00:00",
    )


def test_canonical_standings_retains_source_facts_and_derives_locally() -> None:
    rows = [
        {
            "position": 2,
            "stage": "Regular Season",
            "group": {"name": "American League"},
            "games": {
                "played": 160,
                "win": {"total": 90, "percentage": ".563"},
                "lose": {"total": 70, "percentage": ".438"},
            },
            "points": {"for": 800, "against": 720},
            "team": {"id": 22, "name": "Example Team"},
        }
    ]

    records = canonical_standings(
        rows,
        _receipt(),
        league_id=1,
        season=2026,
    )

    assert len(records) == 1
    record = records[0]
    assert record.team_id == 22
    assert record.games_played == 160
    assert record.run_differential == 80.0
    assert record.runs_per_game == 5.0
    assert record.runs_allowed_per_game == 4.5
    assert record.source_payload_ref == "s3://raw/provider.json"


def test_canonical_team_statistics_matches_verified_object_schema() -> None:
    payload = {
        "team": {"id": 22, "name": "Example Team"},
        "league": {"id": 1, "season": 2026},
        "games": {
            "played": {"all": 160, "home": 80, "away": 80},
            "wins": {
                "all": {"total": 90, "percentage": ".563"},
                "home": {"total": 50, "percentage": ".625"},
                "away": {"total": 40, "percentage": ".500"},
            },
            "loses": {
                "all": {"total": 70, "percentage": ".438"},
                "home": {"total": 30, "percentage": ".375"},
                "away": {"total": 40, "percentage": ".500"},
            },
        },
        "points": {
            "for": {
                "total": {"all": 800, "home": 430, "away": 370},
                "average": {"all": "5.0", "home": "5.375", "away": "4.625"},
            },
            "against": {
                "total": {"all": 720, "home": 330, "away": 390},
                "average": {"all": "4.5", "home": "4.125", "away": "4.875"},
            },
        },
    }

    record = canonical_team_statistics(payload, _receipt())

    assert record.team_id == 22
    assert record.games_played_home == 80
    assert record.win_pct_home == 0.625
    assert record.runs_for_avg_away == 4.625
    assert record.runs_against_avg_home == 4.125
    assert record.compact_features(side="home") == {
        "sample_games": 80,
        "win_pct": 0.625,
        "runs_per_game": 5.375,
        "runs_allowed_per_game": 4.125,
        "run_differential_per_game": 1.25,
    }


def test_reference_catalog_is_identity_only_not_market_availability() -> None:
    record = canonical_reference_catalog(
        [
            {"id": 1, "name": "Home/Away"},
            {"id": 5, "name": "Over/Under"},
        ],
        _receipt(),
        catalog_type="BET_TYPES",
    )

    assert record.entries == ((1, "Home/Away"), (5, "Over/Under"))
    assert not hasattr(record, "available_for_game")
