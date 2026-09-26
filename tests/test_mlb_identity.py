from datetime import UTC, datetime, timedelta

import pytest

from quantbot.baseball.evidence import EvidenceError
from quantbot.baseball.fixture_evidence import FixtureObservation
from quantbot.baseball.mlb_identity import (
    MLBTeamIdentityRegistry,
    link_fixture_to_mlb_game,
    propose_team_identity_mappings,
)
from quantbot.baseball.raw_archive import ArchiveReceipt


def _fixture(*, league="MLB"):
    return FixtureObservation(
        fixture_observation_id="11111111-1111-4111-8111-111111111111",
        game_id="186584",
        provider="api-sports-baseball",
        provider_game_id=186584,
        league=league,
        home_team_id=2001,
        home_team_name="New York Mets",
        away_team_id=2002,
        away_team_name="Philadelphia Phillies",
        kickoff_at="2026-09-20T17:10:00+00:00",
        provider_status="NS",
        observed_at="2026-09-20T13:00:00+00:00",
        source_payload_ref="s3://raw/api-sports/games.json",
        source_payload_checksum="a" * 64,
        schema_version="1.0",
    )


def _receipt():
    return ArchiveReceipt(
        ref="s3://raw/official-mlb/schedule.json",
        checksum="b" * 64,
        captured_at="2026-09-20T13:05:00+00:00",
    )


def _schedule(*, game_pk=823570, first_pitch="2026-09-20T17:12:00Z"):
    return {
        "dates": [
            {
                "date": "2026-09-20",
                "games": [
                    {
                        "gamePk": game_pk,
                        "gameDate": first_pitch,
                        "teams": {
                            "home": {
                                "team": {
                                    "id": 121,
                                    "name": "New York Mets",
                                }
                            },
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


def _registry():
    mappings = propose_team_identity_mappings(
        _fixture(),
        _schedule(),
        _receipt(),
        mapping_version="mlb-2026-v1",
        verified_at=datetime(2026, 9, 20, 13, 5, tzinfo=UTC),
    )
    return MLBTeamIdentityRegistry(mappings), mappings


def test_bootstrap_then_link_uses_versioned_team_ids_and_time() -> None:
    registry, mappings = _registry()

    assert {row.api_sports_team_id for row in mappings} == {2001, 2002}
    assert {row.official_mlb_team_id for row in mappings} == {121, 143}

    link = link_fixture_to_mlb_game(
        _fixture(),
        _schedule(),
        _receipt(),
        registry,
    )

    assert link.game_id == "186584"
    assert link.mlb_game_pk == 823570
    assert link.mapping_version == "mlb-2026-v1"
    assert link.mlb_home_team_id == 121
    assert link.mlb_away_team_id == 143
    assert link.kickoff_delta_seconds == 120
    assert link.api_source_payload_checksum == "a" * 64
    assert link.mlb_schedule_source_payload_checksum == "b" * 64


def test_production_link_fails_when_team_registry_is_incomplete() -> None:
    _, mappings = _registry()
    registry = MLBTeamIdentityRegistry((mappings[0],))

    with pytest.raises(EvidenceError, match="absent from MLB identity registry"):
        link_fixture_to_mlb_game(
            _fixture(),
            _schedule(),
            _receipt(),
            registry,
        )


def test_production_link_fails_on_ambiguous_schedule_identity() -> None:
    registry, _ = _registry()
    schedule = _schedule()
    duplicate = dict(schedule["dates"][0]["games"][0])
    duplicate["gamePk"] = 823571
    schedule["dates"][0]["games"].append(duplicate)

    with pytest.raises(EvidenceError, match="exactly one ID/time match"):
        link_fixture_to_mlb_game(
            _fixture(),
            schedule,
            _receipt(),
            registry,
        )


def test_production_link_fails_outside_first_pitch_tolerance() -> None:
    registry, _ = _registry()

    with pytest.raises(EvidenceError, match="exactly one ID/time match"):
        link_fixture_to_mlb_game(
            _fixture(),
            _schedule(first_pitch="2026-09-20T17:50:00Z"),
            _receipt(),
            registry,
            kickoff_tolerance=timedelta(minutes=30),
        )


def test_bootstrap_requires_exact_team_names_not_fuzzy_aliases() -> None:
    schedule = _schedule()
    schedule["dates"][0]["games"][0]["teams"]["home"]["team"]["name"] = "NY Mets"

    with pytest.raises(EvidenceError, match="exactly one exact-name/time match"):
        propose_team_identity_mappings(
            _fixture(),
            schedule,
            _receipt(),
            mapping_version="mlb-2026-v1",
        )


def test_identity_bridge_rejects_non_mlb_fixture() -> None:
    with pytest.raises(EvidenceError, match="MLB fixtures only"):
        propose_team_identity_mappings(
            _fixture(league="NPB"),
            _schedule(),
            _receipt(),
            mapping_version="mlb-2026-v1",
        )
