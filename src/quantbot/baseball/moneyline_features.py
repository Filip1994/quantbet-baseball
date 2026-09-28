"""Point-in-time Moneyline V1 feature assembly.

The V1 contract is deliberately compact. It combines API-Sports team-strength
rates with Official MLB pregame state without treating identifiers as numeric
strength signals. Every input must have been known by the requested cutoff.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Protocol

from .evidence import EvidenceError
from .feature_snapshot import FeatureSnapshot, FeatureSource, build_feature_snapshot
from .fixture_evidence import FixtureObservation
from .mlb_identity import MLBGameIdentityLink
from .official_mlb_components import OfficialMLBPregameComponent
from .provider_data import TeamStatisticsSnapshot

FEATURE_VERSION = "moneyline-v1"
MLB_API_SPORTS_LEAGUE_ID = 1

_EXPECTED_COMPONENT_KEYS = {
    ("STARTER", "AWAY"),
    ("STARTER", "HOME"),
    ("LINEUP", "AWAY"),
    ("LINEUP", "HOME"),
    ("BULLPEN", "AWAY"),
    ("BULLPEN", "HOME"),
    ("VENUE", "GAME"),
}


class FixtureRepository(Protocol):
    def latest_fixture_observation(
        self,
        *,
        game_id: str,
        as_of: datetime,
    ) -> FixtureObservation | None: ...


class IdentityRepository(Protocol):
    def game_link_for_provider_game(
        self,
        *,
        mapping_version: str,
        provider_game_id: int,
    ) -> MLBGameIdentityLink | None: ...


class ProviderDataRepository(Protocol):
    def latest_team_statistics(
        self,
        *,
        league_id: int,
        season: int,
        team_id: int,
        as_of: datetime,
    ) -> TeamStatisticsSnapshot | None: ...


class ComponentRepository(Protocol):
    def latest_components_for_game(
        self,
        *,
        mlb_game_pk: int,
        as_of: datetime,
    ) -> tuple[OfficialMLBPregameComponent, ...]: ...


class FeatureSnapshotRepository(Protocol):
    def append(self, snapshot: FeatureSnapshot) -> bool: ...


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def _require_component_set(
    components: tuple[OfficialMLBPregameComponent, ...],
) -> dict[tuple[str, str], OfficialMLBPregameComponent]:
    by_key: dict[tuple[str, str], OfficialMLBPregameComponent] = {}
    for component in components:
        key = (component.component_type, component.side)
        if key in by_key:
            raise EvidenceError("duplicate Official MLB component key")
        by_key[key] = component
    if set(by_key) != _EXPECTED_COMPONENT_KEYS:
        missing = sorted(_EXPECTED_COMPONENT_KEYS - set(by_key))
        extra = sorted(set(by_key) - _EXPECTED_COMPONENT_KEYS)
        raise EvidenceError(
            f"incomplete Official MLB component set; missing={missing}; extra={extra}"
        )
    return by_key


def _team_features(
    record: TeamStatisticsSnapshot,
    *,
    prefix: str,
    context_side: str,
) -> tuple[dict[str, float | int], tuple[str, ...]]:
    overall = record.compact_features()
    contextual = record.compact_features(side=context_side)
    features: dict[str, float | int] = {}
    for scope, values in (("overall", overall), ("context", contextual)):
        for name, value in values.items():
            features[f"{prefix}_{scope}_{name}"] = value
    return features, tuple(sorted(features))


def _list_size(value: object) -> int:
    return len(value) if isinstance(value, list) else 0


def _optional_feature(
    features: dict[str, object],
    null_reasons: dict[str, str],
    *,
    name: str,
    value: object,
    reason: str,
) -> None:
    if value is None or value == "":
        features[name] = None
        null_reasons[name] = reason
    else:
        features[name] = value


def _component_sources(
    contributions: tuple[
        tuple[OfficialMLBPregameComponent, tuple[str, ...]],
        ...,
    ],
) -> tuple[FeatureSource, ...]:
    grouped: dict[
        tuple[str, str, str, str],
        set[str],
    ] = defaultdict(set)
    for component, fields in contributions:
        key = (
            component.source_payload_ref,
            component.source_payload_checksum,
            component.source_observed_at,
            component.retrieved_at,
        )
        grouped[key].update(fields)

    rows: list[FeatureSource] = []
    for (
        source_ref,
        checksum,
        observed_at,
        retrieved_at,
    ), field_names in sorted(grouped.items()):
        rows.append(
            FeatureSource(
                source_name="official-mlb-stats-api:pregame",
                observed_at=observed_at,
                retrieved_at=retrieved_at,
                source_payload_ref=source_ref,
                source_payload_checksum=checksum,
                field_names=tuple(sorted(field_names)),
            )
        )
    return tuple(rows)


def build_moneyline_v1_feature_snapshot(
    *,
    fixture: FixtureObservation,
    identity_link: MLBGameIdentityLink,
    home_team_statistics: TeamStatisticsSnapshot,
    away_team_statistics: TeamStatisticsSnapshot,
    components: tuple[OfficialMLBPregameComponent, ...],
    generated_at: datetime,
) -> FeatureSnapshot:
    """Build one deterministic, leakage-safe MLB Moneyline V1 feature snapshot."""

    generated = _utc(generated_at, "generated_at")
    if fixture.league.strip().casefold() != "mlb":
        raise EvidenceError("Moneyline V1 assembler accepts MLB fixtures only")
    if fixture.game_id != identity_link.game_id:
        raise EvidenceError("fixture and MLB identity link game mismatch")
    if fixture.provider_game_id != identity_link.api_sports_provider_game_id:
        raise EvidenceError("provider game identity mismatch")
    if (
        fixture.home_team_id != identity_link.api_home_team_id
        or fixture.away_team_id != identity_link.api_away_team_id
    ):
        raise EvidenceError("fixture teams disagree with MLB identity link")

    fixture_kickoff = _timestamp(fixture.kickoff_at, "fixture.kickoff_at")
    official_kickoff = _timestamp(
        identity_link.official_mlb_first_pitch,
        "identity_link.official_mlb_first_pitch",
    )
    if generated >= fixture_kickoff or generated >= official_kickoff:
        raise EvidenceError("feature snapshot must be assembled before first pitch")

    if home_team_statistics.team_id != fixture.home_team_id:
        raise EvidenceError("home team statistics identity mismatch")
    if away_team_statistics.team_id != fixture.away_team_id:
        raise EvidenceError("away team statistics identity mismatch")
    if (
        home_team_statistics.league_id != away_team_statistics.league_id
        or home_team_statistics.season != away_team_statistics.season
    ):
        raise EvidenceError("team statistics league/season mismatch")
    for side, stats in (
        ("home", home_team_statistics),
        ("away", away_team_statistics),
    ):
        if _timestamp(stats.observed_at, f"{side}_team_statistics.observed_at") > generated:
            raise EvidenceError(f"{side} team statistics were not known by cutoff")

    by_key = _require_component_set(components)
    for component in components:
        if component.mlb_game_pk != identity_link.mlb_game_pk:
            raise EvidenceError("Official MLB component game identity mismatch")
        if _timestamp(component.retrieved_at, "component.retrieved_at") > generated:
            raise EvidenceError("Official MLB component was not known by cutoff")
        component_pitch = _timestamp(
            component.scheduled_first_pitch,
            "component.scheduled_first_pitch",
        )
        if generated >= component_pitch:
            raise EvidenceError("Official MLB component is not safely pregame")

    features: dict[str, object] = {}
    null_reasons: dict[str, str] = {}
    sources: list[FeatureSource] = []

    home_features, home_fields = _team_features(
        home_team_statistics,
        prefix="home",
        context_side="home",
    )
    away_features, away_fields = _team_features(
        away_team_statistics,
        prefix="away",
        context_side="away",
    )
    features.update(home_features)
    features.update(away_features)

    sources.extend(
        (
            FeatureSource(
                source_name="api-sports-baseball:team-statistics:home",
                observed_at=home_team_statistics.observed_at,
                retrieved_at=home_team_statistics.observed_at,
                source_payload_ref=home_team_statistics.source_payload_ref,
                source_payload_checksum=home_team_statistics.source_payload_checksum,
                field_names=home_fields,
            ),
            FeatureSource(
                source_name="api-sports-baseball:team-statistics:away",
                observed_at=away_team_statistics.observed_at,
                retrieved_at=away_team_statistics.observed_at,
                source_payload_ref=away_team_statistics.source_payload_ref,
                source_payload_checksum=away_team_statistics.source_payload_checksum,
                field_names=away_fields,
            ),
        )
    )

    home_starter = by_key[("STARTER", "HOME")]
    away_starter = by_key[("STARTER", "AWAY")]
    home_lineup = by_key[("LINEUP", "HOME")]
    away_lineup = by_key[("LINEUP", "AWAY")]
    home_bullpen = by_key[("BULLPEN", "HOME")]
    away_bullpen = by_key[("BULLPEN", "AWAY")]
    venue = by_key[("VENUE", "GAME")]

    starter_fields = (
        "home_starter_state",
        "home_starter_identified",
        "away_starter_state",
        "away_starter_identified",
    )
    features["home_starter_state"] = home_starter.state
    features["home_starter_identified"] = home_starter.state != "ABSENT"
    features["away_starter_state"] = away_starter.state
    features["away_starter_identified"] = away_starter.state != "ABSENT"

    lineup_fields = (
        "home_lineup_state",
        "home_lineup_slots",
        "home_lineup_populated",
        "away_lineup_state",
        "away_lineup_slots",
        "away_lineup_populated",
    )
    features["home_lineup_state"] = home_lineup.state
    features["home_lineup_slots"] = _list_size(
        home_lineup.data.get("batting_order_ids")
    )
    features["home_lineup_populated"] = home_lineup.state == "POPULATED"
    features["away_lineup_state"] = away_lineup.state
    features["away_lineup_slots"] = _list_size(
        away_lineup.data.get("batting_order_ids")
    )
    features["away_lineup_populated"] = away_lineup.state == "POPULATED"

    bullpen_fields = (
        "home_bullpen_state",
        "home_bullpen_members",
        "away_bullpen_state",
        "away_bullpen_members",
    )
    features["home_bullpen_state"] = home_bullpen.state
    features["home_bullpen_members"] = _list_size(
        home_bullpen.data.get("pitcher_ids")
    )
    features["away_bullpen_state"] = away_bullpen.state
    features["away_bullpen_members"] = _list_size(
        away_bullpen.data.get("pitcher_ids")
    )

    venue_fields = (
        "venue_id",
        "venue_roof_type",
        "venue_turf_type",
        "venue_elevation_ft",
    )
    venue_id = venue.data.get("venue_id")
    _optional_feature(
        features,
        null_reasons,
        name="venue_id",
        value=None if venue_id is None else str(venue_id),
        reason="OFFICIAL_MLB_VENUE_ID_MISSING",
    )
    _optional_feature(
        features,
        null_reasons,
        name="venue_roof_type",
        value=venue.data.get("roof_type"),
        reason="OFFICIAL_MLB_ROOF_TYPE_MISSING",
    )
    _optional_feature(
        features,
        null_reasons,
        name="venue_turf_type",
        value=venue.data.get("turf_type"),
        reason="OFFICIAL_MLB_TURF_TYPE_MISSING",
    )
    _optional_feature(
        features,
        null_reasons,
        name="venue_elevation_ft",
        value=venue.data.get("elevation_ft"),
        reason="OFFICIAL_MLB_ELEVATION_MISSING",
    )

    sources.extend(
        _component_sources(
            (
                (home_starter, starter_fields[:2]),
                (away_starter, starter_fields[2:]),
                (home_lineup, lineup_fields[:3]),
                (away_lineup, lineup_fields[3:]),
                (home_bullpen, bullpen_fields[:2]),
                (away_bullpen, bullpen_fields[2:]),
                (venue, venue_fields),
            )
        )
    )

    return build_feature_snapshot(
        game_id=fixture.game_id,
        feature_version=FEATURE_VERSION,
        generated_at=generated.isoformat(),
        kickoff_at=fixture_kickoff.isoformat(),
        features=features,
        sources=tuple(sources),
        null_reasons=null_reasons,
    )


def assemble_moneyline_v1_feature_snapshot(
    fixture_repository: FixtureRepository,
    identity_repository: IdentityRepository,
    provider_repository: ProviderDataRepository,
    component_repository: ComponentRepository,
    *,
    provider_game_id: int,
    mapping_version: str,
    as_of: datetime,
    league_id: int = MLB_API_SPORTS_LEAGUE_ID,
    season: int | None = None,
) -> FeatureSnapshot:
    """Resolve all point-in-time evidence and build one V1 snapshot or fail closed."""

    cutoff = _utc(as_of, "as_of")
    game_id = str(provider_game_id)
    fixture = fixture_repository.latest_fixture_observation(
        game_id=game_id,
        as_of=cutoff,
    )
    if fixture is None:
        raise EvidenceError("no fixture evidence is available by cutoff")

    identity_link = identity_repository.game_link_for_provider_game(
        mapping_version=mapping_version,
        provider_game_id=provider_game_id,
    )
    if identity_link is None:
        raise EvidenceError("fixture has no verified Official MLB game link")

    target_season = season or _timestamp(fixture.kickoff_at, "fixture.kickoff_at").year
    home_stats = provider_repository.latest_team_statistics(
        league_id=league_id,
        season=target_season,
        team_id=fixture.home_team_id,
        as_of=cutoff,
    )
    away_stats = provider_repository.latest_team_statistics(
        league_id=league_id,
        season=target_season,
        team_id=fixture.away_team_id,
        as_of=cutoff,
    )
    if home_stats is None or away_stats is None:
        raise EvidenceError("complete team statistics are unavailable by cutoff")

    components = component_repository.latest_components_for_game(
        mlb_game_pk=identity_link.mlb_game_pk,
        as_of=cutoff,
    )
    return build_moneyline_v1_feature_snapshot(
        fixture=fixture,
        identity_link=identity_link,
        home_team_statistics=home_stats,
        away_team_statistics=away_stats,
        components=components,
        generated_at=cutoff,
    )


def assemble_and_persist_moneyline_v1_feature_snapshot(
    fixture_repository: FixtureRepository,
    identity_repository: IdentityRepository,
    provider_repository: ProviderDataRepository,
    component_repository: ComponentRepository,
    feature_repository: FeatureSnapshotRepository,
    *,
    provider_game_id: int,
    mapping_version: str,
    as_of: datetime,
    league_id: int = MLB_API_SPORTS_LEAGUE_ID,
    season: int | None = None,
) -> tuple[FeatureSnapshot, bool]:
    snapshot = assemble_moneyline_v1_feature_snapshot(
        fixture_repository,
        identity_repository,
        provider_repository,
        component_repository,
        provider_game_id=provider_game_id,
        mapping_version=mapping_version,
        as_of=as_of,
        league_id=league_id,
        season=season,
    )
    return snapshot, feature_repository.append(snapshot)
