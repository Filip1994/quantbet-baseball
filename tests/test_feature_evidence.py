import pytest

from quantbot.baseball.evidence import EvidenceError
from quantbot.baseball.feature_evidence import (
    FeatureSource,
    build_pregame_feature_snapshot,
    canonical_feature_snapshot_json,
)


def _source(
    *, available_at: str = "2026-09-26T16:55:00+00:00"
) -> FeatureSource:
    return FeatureSource(
        provider="api-sports-baseball",
        source_type="team_statistics",
        observed_at="2026-09-26T16:54:00+00:00",
        available_at=available_at,
        source_payload_ref="s3://raw/team-statistics.json",
        source_payload_checksum="a" * 64,
        feature_paths=("home.offense.runs_per_game",),
    )


def test_builds_deterministic_point_in_time_snapshot() -> None:
    args = {
        "game_id": "123",
        "feature_set_version": "pregame-v1",
        "source_data_cutoff_at": "2026-09-26T17:00:00+00:00",
        "generated_at": "2026-09-26T17:00:30+00:00",
        "kickoff_at": "2026-09-26T19:00:00+00:00",
        "features": {
            "home": {"offense": {"runs_per_game": 4.8}},
            "weather": {"available": False},
        },
        "sources": (_source(),),
    }

    first = build_pregame_feature_snapshot(**args)
    second = build_pregame_feature_snapshot(**args)

    assert first == second
    assert first.feature_snapshot_id == second.feature_snapshot_id
    assert first.ref.startswith("feature://pregame/")
    assert '"runs_per_game":4.8' in canonical_feature_snapshot_json(first)


def test_rejects_source_not_available_by_cutoff() -> None:
    with pytest.raises(EvidenceError, match="not available by cutoff"):
        build_pregame_feature_snapshot(
            game_id="123",
            feature_set_version="pregame-v1",
            source_data_cutoff_at="2026-09-26T17:00:00+00:00",
            generated_at="2026-09-26T17:00:30+00:00",
            kickoff_at="2026-09-26T19:00:00+00:00",
            features={"home": {"rating": 1.0}},
            sources=(
                _source(available_at="2026-09-26T17:01:00+00:00"),
            ),
        )


def test_rejects_snapshot_at_or_after_first_pitch() -> None:
    with pytest.raises(EvidenceError, match="before kickoff"):
        build_pregame_feature_snapshot(
            game_id="123",
            feature_set_version="pregame-v1",
            source_data_cutoff_at="2026-09-26T18:59:00+00:00",
            generated_at="2026-09-26T19:00:00+00:00",
            kickoff_at="2026-09-26T19:00:00+00:00",
            features={"home": {"rating": 1.0}},
            sources=(_source(),),
        )


def test_rejects_non_finite_feature_values() -> None:
    with pytest.raises(EvidenceError, match="non-finite"):
        build_pregame_feature_snapshot(
            game_id="123",
            feature_set_version="pregame-v1",
            source_data_cutoff_at="2026-09-26T17:00:00+00:00",
            generated_at="2026-09-26T17:00:30+00:00",
            kickoff_at="2026-09-26T19:00:00+00:00",
            features={"weather": {"temperature_c": float("nan")}},
            sources=(_source(),),
        )
