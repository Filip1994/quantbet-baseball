import json

import pytest

from quantbot.baseball.evidence import EvidenceError
from quantbot.baseball.feature_snapshot import (
    FeatureSource,
    build_feature_snapshot,
    canonical_feature_snapshot_json,
)


def _source(
    *,
    name: str = "api-sports-games",
    observed_at: str = "2030-07-04T16:00:00+00:00",
    ref: str = "s3://raw/source.json",
) -> FeatureSource:
    return FeatureSource(
        source_name=name,
        observed_at=observed_at,
        source_payload_ref=ref,
        source_payload_checksum="a" * 64,
        field_names=("home_team_id", "away_team_id"),
    )


def test_builds_deterministic_point_in_time_snapshot() -> None:
    source = _source()
    kwargs = {
        "game_id": "123",
        "feature_version": "research-v1",
        "generated_at": "2030-07-04T16:05:00+00:00",
        "kickoff_at": "2030-07-04T19:20:00+00:00",
        "features": {
            "home_rest_hours": 48.0,
            "weather_temperature_c": None,
        },
        "sources": (source,),
        "null_reasons": {
            "weather_temperature_c": "ROOF_CLOSED",
        },
    }

    first = build_feature_snapshot(**kwargs)
    second = build_feature_snapshot(**kwargs)

    assert first == second
    assert first.snapshot_id == second.snapshot_id
    assert first.source_data_cutoff_at == "2030-07-04T16:00:00+00:00"
    assert json.loads(canonical_feature_snapshot_json(first))["game_id"] == "123"


def test_latest_source_timestamp_becomes_cutoff() -> None:
    early = _source()
    late = _source(
        name="open-meteo",
        observed_at="2030-07-04T16:03:00+00:00",
        ref="s3://raw/weather.json",
    )

    snapshot = build_feature_snapshot(
        game_id="123",
        feature_version="research-v1",
        generated_at="2030-07-04T16:05:00+00:00",
        kickoff_at="2030-07-04T19:20:00+00:00",
        features={"temperature_c": 27.5},
        sources=(early, late),
    )

    assert snapshot.source_data_cutoff_at == "2030-07-04T16:03:00+00:00"


def test_null_feature_requires_reason() -> None:
    with pytest.raises(EvidenceError):
        build_feature_snapshot(
            game_id="123",
            feature_version="research-v1",
            generated_at="2030-07-04T16:05:00+00:00",
            kickoff_at="2030-07-04T19:20:00+00:00",
            features={"probable_starter_id": None},
            sources=(_source(),),
        )


def test_rejects_source_observed_after_snapshot_generation() -> None:
    with pytest.raises(EvidenceError):
        build_feature_snapshot(
            game_id="123",
            feature_version="research-v1",
            generated_at="2030-07-04T16:05:00+00:00",
            kickoff_at="2030-07-04T19:20:00+00:00",
            features={"home_rest_hours": 48.0},
            sources=(
                _source(observed_at="2030-07-04T16:06:00+00:00"),
            ),
        )


def test_rejects_post_kickoff_snapshot() -> None:
    with pytest.raises(EvidenceError):
        build_feature_snapshot(
            game_id="123",
            feature_version="research-v1",
            generated_at="2030-07-04T19:20:00+00:00",
            kickoff_at="2030-07-04T19:20:00+00:00",
            features={"home_rest_hours": 48.0},
            sources=(_source(),),
        )
