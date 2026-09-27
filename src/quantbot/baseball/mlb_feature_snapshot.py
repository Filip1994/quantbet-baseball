"""MLB-native assembly of model-admissible point-in-time feature snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from .evidence import EvidenceError
from .feature_snapshot import FeatureSnapshot, FeatureSource, build_feature_snapshot
from .mlb_identity import MLBGameIdentityLink
from .official_mlb_components import OfficialMLBPregameComponent
from .provider_data import TeamStatisticsSnapshot

_EXPECTED_COMPONENT_KEYS = {
    ("STARTER", "AWAY"),
    ("STARTER", "HOME"),
    ("LINEUP", "AWAY"),
    ("LINEUP", "HOME"),
    ("BULLPEN", "AWAY"),
    ("BULLPEN", "HOME"),
    ("VENUE", "GAME"),
}
_TEAM_STAT_FEATURES = (
    "sample_games",
    "win_pct",
    "runs_per_game",
    "runs_allowed_per_game",
    "run_differential_per_game",
)


def _timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def _generated_at(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    return value.astimezone(UTC)


def _component_map(
    components: tuple[OfficialMLBPregameComponent, ...],
) -> dict[tuple[str, str], OfficialMLBPregameComponent]:
    rows = {(row.component_type, row.side): row for row in components}
    if len(components) != 7 or set(rows) != _EXPECTED_COMPONENT_KEYS:
        raise EvidenceError("MLB feature snapshot requires exactly seven components")
    return rows


def _sequence_count(value: Any, field: str) -> int:
    if not isinstance(value, list):
        raise EvidenceError(f"{field} must be a list")
    return len(value)


def _source_groups() -> dict[
    tuple[str, str, str, str, str],
    set[str],
]:
    return {}


def _add_source(
    groups: dict[tuple[str, str, str, str, str], set[str]],
    *,
    source_name: str,
    observed_at: str,
    retrieved_at: str,
    source_payload_ref: str,
    source_payload_checksum: str,
    field_names: tuple[str, ...],
) -> None:
    key = (
        source_name,
        observed_at,
        retrieved_at,
        source_payload_ref,
        source_payload_checksum,
    )
    groups.setdefault(key, set()).update(field_names)


def _feature_sources(
    groups: Mapping[tuple[str, str, str, str, str], set[str]],
) -> tuple[FeatureSource, ...]:
    rows: list[FeatureSource] = []
    for key in sorted(groups):
        source_name, observed_at, retrieved_at, ref, checksum = key
        rows.append(
            FeatureSource(
                source_name=source_name,
                observed_at=observed_at,
                retrieved_at=retrieved_at,
                source_payload_ref=ref,
                source_payload_checksum=checksum,
                field_names=tuple(sorted(groups[key])),
            )
        )
    return tuple(rows)


def _add_team_statistics(
    *,
    side: str,
    record: TeamStatisticsSnapshot | None,
    expected_team_id: int,
    features: dict[str, Any],
    null_reasons: dict[str, str],
    sources: dict[tuple[str, str, str, str, str], set[str]],
) -> None:
    prefix = f"{side}_team"
    names = tuple(f"{prefix}_{name}" for name in _TEAM_STAT_FEATURES)
    if record is None:
        for name in names:
            features[name] = None
            null_reasons[name] = "TEAM_STATISTICS_UNAVAILABLE_AT_CUTOFF"
        return
    if int(record.team_id) != int(expected_team_id):
        raise EvidenceError(f"{side} team statistics identity mismatch")

    compact = record.compact_features(side=side)
    for suffix in _TEAM_STAT_FEATURES:
        features[f"{prefix}_{suffix}"] = compact[suffix]

    _add_source(
        sources,
        source_name="api-sports-baseball-team-statistics",
        observed_at=record.observed_at,
        retrieved_at=record.observed_at,
        source_payload_ref=record.source_payload_ref,
        source_payload_checksum=record.source_payload_checksum,
        field_names=names,
    )


def compose_mlb_pregame_feature_snapshot(
    *,
    link: MLBGameIdentityLink,
    components: tuple[OfficialMLBPregameComponent, ...],
    home_team_statistics: TeamStatisticsSnapshot | None,
    away_team_statistics: TeamStatisticsSnapshot | None,
    generated_at: datetime,
    feature_version: str = "mlb-pregame-v1",
) -> FeatureSnapshot:
    """Compose one MLB feature snapshot from evidence known by generated_at.

    This v1 deliberately keeps identity IDs out of the numeric model vector.
    Starter, lineup and bullpen evidence is represented only through model-safe
    state/count features until quality/fatigue estimators have their own PIT
    contracts.
    """

    generated = _generated_at(generated_at)
    kickoff = _timestamp(link.official_mlb_first_pitch, "official_mlb_first_pitch")
    if generated >= kickoff:
        raise EvidenceError("MLB feature snapshot must be generated before first pitch")

    by_key = _component_map(components)
    source_groups = _source_groups()
    features: dict[str, Any] = {}
    null_reasons: dict[str, str] = {}

    component_fields: dict[tuple[str, str], tuple[str, ...]] = {
        ("STARTER", "HOME"): ("home_starter_known", "home_starter_state"),
        ("STARTER", "AWAY"): ("away_starter_known", "away_starter_state"),
        ("LINEUP", "HOME"): ("home_lineup_state", "home_lineup_count"),
        ("LINEUP", "AWAY"): ("away_lineup_state", "away_lineup_count"),
        ("BULLPEN", "HOME"): ("home_bullpen_state", "home_bullpen_count"),
        ("BULLPEN", "AWAY"): ("away_bullpen_state", "away_bullpen_count"),
        ("VENUE", "GAME"): (
            "venue_roof_type",
            "venue_turf_type",
            "venue_elevation_ft",
        ),
    }

    for key, row in by_key.items():
        if row.mlb_game_pk != link.mlb_game_pk:
            raise EvidenceError("MLB feature component game identity mismatch")
        if _timestamp(row.scheduled_first_pitch, "component.scheduled_first_pitch") != (
            kickoff
        ):
            raise EvidenceError("MLB feature component first pitch mismatch")
        observed = _timestamp(row.source_observed_at, "component.source_observed_at")
        retrieved = _timestamp(row.retrieved_at, "component.retrieved_at")
        if retrieved < observed:
            raise EvidenceError("component retrieval cannot precede observation")
        if retrieved > generated:
            raise EvidenceError("MLB feature component was unavailable at generated_at")
        if retrieved >= kickoff:
            raise EvidenceError("MLB feature component was retrieved after first pitch")

        _add_source(
            source_groups,
            source_name="official-mlb-pregame",
            observed_at=row.source_observed_at,
            retrieved_at=row.retrieved_at,
            source_payload_ref=row.source_payload_ref,
            source_payload_checksum=row.source_payload_checksum,
            field_names=component_fields[key],
        )

    for side in ("home", "away"):
        upper = side.upper()
        starter = by_key[("STARTER", upper)]
        lineup = by_key[("LINEUP", upper)]
        bullpen = by_key[("BULLPEN", upper)]

        pitcher_id = starter.data.get("pitcher_id")
        if pitcher_id is not None and (
            isinstance(pitcher_id, bool)
            or not isinstance(pitcher_id, int)
            or pitcher_id <= 0
        ):
            raise EvidenceError(f"{side} starter pitcher_id is invalid")
        features[f"{side}_starter_known"] = pitcher_id is not None
        features[f"{side}_starter_state"] = starter.state
        features[f"{side}_lineup_state"] = lineup.state
        features[f"{side}_lineup_count"] = _sequence_count(
            lineup.data.get("batting_order_ids"),
            f"{side}.batting_order_ids",
        )
        features[f"{side}_bullpen_state"] = bullpen.state
        features[f"{side}_bullpen_count"] = _sequence_count(
            bullpen.data.get("pitcher_ids"),
            f"{side}.bullpen.pitcher_ids",
        )

    venue = by_key[("VENUE", "GAME")]
    for name, raw_key in (
        ("venue_roof_type", "roof_type"),
        ("venue_turf_type", "turf_type"),
        ("venue_elevation_ft", "elevation_ft"),
    ):
        value = venue.data.get(raw_key)
        features[name] = value
        if value is None:
            null_reasons[name] = "VENUE_FIELD_UNAVAILABLE_AT_CUTOFF"

    _add_team_statistics(
        side="home",
        record=home_team_statistics,
        expected_team_id=link.api_home_team_id,
        features=features,
        null_reasons=null_reasons,
        sources=source_groups,
    )
    _add_team_statistics(
        side="away",
        record=away_team_statistics,
        expected_team_id=link.api_away_team_id,
        features=features,
        null_reasons=null_reasons,
        sources=source_groups,
    )

    return build_feature_snapshot(
        game_id=link.game_id,
        feature_version=feature_version,
        generated_at=generated.isoformat(),
        kickoff_at=kickoff.isoformat(),
        features=features,
        sources=_feature_sources(source_groups),
        null_reasons=null_reasons,
    )
