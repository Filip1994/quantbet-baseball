"""Component-level point-in-time evidence from the Official MLB pregame feed."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from .evidence import EvidenceError
from .official_mlb import OfficialMLBPregameSnapshot, canonical_pregame_snapshot
from .raw_archive import ArchiveReceipt

_COMPONENT_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/official-mlb-pregame-component/v1",
)
_PROVIDER = "official-mlb-stats-api"
_COMPONENT_SIDES = {
    "STARTER": {"AWAY", "HOME"},
    "LINEUP": {"AWAY", "HOME"},
    "BULLPEN": {"AWAY", "HOME"},
    "VENUE": {"GAME"},
}
_COMPONENT_STATES = {
    "STARTER": {"ABSENT", "PROBABLE", "CONFIRMED"},
    "LINEUP": {"ABSENT", "PARTIAL", "POPULATED"},
    "BULLPEN": {"ABSENT", "PRESENT"},
    "VENUE": {"PRESENT"},
}


def _timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def _nonempty(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise EvidenceError(f"{field} must be non-empty")
    return result


def _checksum(value: str) -> str:
    raw = _nonempty(value, "source_payload_checksum")
    if len(raw) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in raw):
        raise EvidenceError("source_payload_checksum must be a SHA-256 hex digest")
    return raw


def _json_object(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    try:
        json.dumps(
            result,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EvidenceError("component data must be finite JSON") from exc
    return result


@dataclass(frozen=True, slots=True)
class OfficialMLBPregameComponent:
    component_id: str
    mlb_game_pk: int
    provider: str
    component_type: str
    side: str
    state: str
    source_observed_at: str
    retrieved_at: str
    scheduled_first_pitch: str
    requested_timecode: str | None
    data: Mapping[str, Any]
    source_payload_ref: str
    source_payload_checksum: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        try:
            uuid.UUID(self.component_id)
        except (TypeError, ValueError) as exc:
            raise EvidenceError("component_id must be a UUID") from exc
        if int(self.mlb_game_pk) <= 0:
            raise EvidenceError("mlb_game_pk must be positive")
        if self.provider != _PROVIDER:
            raise EvidenceError("official MLB component provider is unsupported")
        if self.component_type not in _COMPONENT_SIDES:
            raise EvidenceError("component_type is unsupported")
        if self.side not in _COMPONENT_SIDES[self.component_type]:
            raise EvidenceError("component side is invalid")
        if self.state not in _COMPONENT_STATES[self.component_type]:
            raise EvidenceError("component state is invalid")
        observed = _timestamp(self.source_observed_at, "source_observed_at")
        retrieved = _timestamp(self.retrieved_at, "retrieved_at")
        kickoff = _timestamp(self.scheduled_first_pitch, "scheduled_first_pitch")
        if observed >= kickoff:
            raise EvidenceError("official MLB component must precede first pitch")
        if retrieved < observed:
            raise EvidenceError("retrieved_at cannot precede source_observed_at")
        _nonempty(self.source_payload_ref, "source_payload_ref")
        _checksum(self.source_payload_checksum)
        _nonempty(self.schema_version, "schema_version")
        _json_object(self.data)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["data"] = dict(self.data)
        return result


def _component(
    snapshot: OfficialMLBPregameSnapshot,
    *,
    component_type: str,
    side: str,
    state: str,
    data: Mapping[str, Any],
) -> OfficialMLBPregameComponent:
    identity = {
        "mlb_game_pk": snapshot.mlb_game_pk,
        "component_type": component_type,
        "side": side,
        "source_observed_at": snapshot.source_observed_at,
        "source_payload_checksum": snapshot.source_payload_checksum,
    }
    component_id = str(
        uuid.uuid5(
            _COMPONENT_NAMESPACE,
            json.dumps(identity, sort_keys=True, separators=(",", ":")),
        )
    )
    return OfficialMLBPregameComponent(
        component_id=component_id,
        mlb_game_pk=snapshot.mlb_game_pk,
        provider=snapshot.provider,
        component_type=component_type,
        side=side,
        state=state,
        source_observed_at=snapshot.source_observed_at,
        retrieved_at=snapshot.retrieved_at,
        scheduled_first_pitch=snapshot.scheduled_first_pitch,
        requested_timecode=snapshot.requested_timecode,
        data=dict(data),
        source_payload_ref=snapshot.source_payload_ref,
        source_payload_checksum=snapshot.source_payload_checksum,
    )


def _lineup_state(ids: tuple[int, ...]) -> str:
    if not ids:
        return "ABSENT"
    if len(ids) >= 9:
        return "POPULATED"
    return "PARTIAL"


def build_pregame_components(
    payload: dict[str, Any],
    receipt: ArchiveReceipt,
    *,
    requested_timecode: str | None = None,
) -> tuple[OfficialMLBPregameComponent, ...]:
    """Split one archived MLB feed into model-safe component evidence.

    A populated batting order is not claimed to be confirmed. Current feed
    canonicalization emits starters only as PROBABLE; CONFIRMED is reserved for
    a future explicit source contract.
    """

    snapshot = canonical_pregame_snapshot(
        payload,
        receipt,
        requested_timecode=requested_timecode,
    )
    rows: list[OfficialMLBPregameComponent] = []

    for side, pitcher_id, pitcher_name in (
        (
            "AWAY",
            snapshot.away_probable_pitcher_id,
            snapshot.away_probable_pitcher_name,
        ),
        (
            "HOME",
            snapshot.home_probable_pitcher_id,
            snapshot.home_probable_pitcher_name,
        ),
    ):
        rows.append(
            _component(
                snapshot,
                component_type="STARTER",
                side=side,
                state="PROBABLE" if pitcher_id is not None else "ABSENT",
                data={
                    "pitcher_id": pitcher_id,
                    "pitcher_name": pitcher_name,
                    "confirmation_state": (
                        "PROBABLE" if pitcher_id is not None else "ABSENT"
                    ),
                },
            )
        )

    for side, order in (
        ("AWAY", snapshot.away_batting_order_ids),
        ("HOME", snapshot.home_batting_order_ids),
    ):
        rows.append(
            _component(
                snapshot,
                component_type="LINEUP",
                side=side,
                state=_lineup_state(order),
                data={
                    "batting_order_ids": list(order),
                    "confirmation_state": "UNVERIFIED",
                },
            )
        )

    for side, bullpen in (
        ("AWAY", snapshot.away_bullpen_ids),
        ("HOME", snapshot.home_bullpen_ids),
    ):
        rows.append(
            _component(
                snapshot,
                component_type="BULLPEN",
                side=side,
                state="PRESENT" if bullpen else "ABSENT",
                data={
                    "pitcher_ids": list(bullpen),
                    "membership_scope": "GAME_FEED_BOXSCORE",
                },
            )
        )

    rows.append(
        _component(
            snapshot,
            component_type="VENUE",
            side="GAME",
            state="PRESENT",
            data={
                "venue_id": snapshot.venue_id,
                "venue_name": snapshot.venue_name,
                "roof_type": snapshot.roof_type,
                "turf_type": snapshot.turf_type,
                "elevation_ft": snapshot.elevation_ft,
                "latitude": snapshot.latitude,
                "longitude": snapshot.longitude,
                "field_azimuth_deg": snapshot.field_azimuth_deg,
                "left_line_ft": snapshot.left_line_ft,
                "left_center_ft": snapshot.left_center_ft,
                "center_ft": snapshot.center_ft,
                "right_center_ft": snapshot.right_center_ft,
                "right_line_ft": snapshot.right_line_ft,
                "venue_timezone": snapshot.venue_timezone,
                "venue_utc_offset_at_game": snapshot.venue_utc_offset_at_game,
            },
        )
    )
    return tuple(rows)


def canonical_component_json(record: OfficialMLBPregameComponent) -> str:
    return json.dumps(
        record.to_dict(),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
