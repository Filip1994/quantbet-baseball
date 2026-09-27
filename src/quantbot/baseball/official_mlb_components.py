"""Component-level point-in-time facts derived from archived Official MLB feeds.

These records deliberately preserve source semantics:
- probablePitchers creates PROBABLE starter evidence, never CONFIRMED.
- boxscore battingOrder creates presence/state evidence, never a confirmation claim.

The records can be backfilled after the fact, so retrieved_at may be later than
first pitch. Live "what did the system know?" queries must constrain both the
provider source timestamp and retrieval timestamp to the requested cutoff.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from .evidence import EvidenceError
from .official_mlb import OfficialMLBPregameSnapshot

_COMPONENT_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/official-mlb-pregame-component/v1",
)


def _timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
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
    checksum = _nonempty(value, "source_payload_checksum")
    if len(checksum) != 64 or any(
        char not in "0123456789abcdefABCDEF" for char in checksum
    ):
        raise EvidenceError("source_payload_checksum must be SHA-256")
    return checksum


def _positive(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise EvidenceError(f"{field} must be a positive integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field} must be a positive integer") from exc
    if number <= 0:
        raise EvidenceError(f"{field} must be a positive integer")
    return number


def _validate_common(
    *,
    mlb_game_pk: int,
    side: str,
    source_observed_at: str,
    retrieved_at: str,
    scheduled_first_pitch: str,
    source_payload_ref: str,
    source_payload_checksum: str,
) -> None:
    _positive(mlb_game_pk, "mlb_game_pk")
    if side not in {"HOME", "AWAY"}:
        raise EvidenceError("side must be HOME or AWAY")
    observed = _timestamp(source_observed_at, "source_observed_at")
    retrieved = _timestamp(retrieved_at, "retrieved_at")
    kickoff = _timestamp(scheduled_first_pitch, "scheduled_first_pitch")
    if observed >= kickoff:
        raise EvidenceError("component source state must precede first pitch")
    if retrieved < observed:
        raise EvidenceError("retrieved_at cannot precede source_observed_at")
    _nonempty(source_payload_ref, "source_payload_ref")
    _checksum(source_payload_checksum)


@dataclass(frozen=True, slots=True)
class OfficialMLBStarterEvidence:
    evidence_id: str
    mlb_game_pk: int
    side: str
    starter_state: str
    pitcher_id: int | None
    pitcher_name: str | None
    source_observed_at: str
    retrieved_at: str
    scheduled_first_pitch: str
    requested_timecode: str | None
    source_payload_ref: str
    source_payload_checksum: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        _nonempty(self.evidence_id, "evidence_id")
        _nonempty(self.schema_version, "schema_version")
        _validate_common(
            mlb_game_pk=self.mlb_game_pk,
            side=self.side,
            source_observed_at=self.source_observed_at,
            retrieved_at=self.retrieved_at,
            scheduled_first_pitch=self.scheduled_first_pitch,
            source_payload_ref=self.source_payload_ref,
            source_payload_checksum=self.source_payload_checksum,
        )
        if self.starter_state not in {"ABSENT", "PROBABLE"}:
            raise EvidenceError("starter_state is unsupported")
        if self.starter_state == "ABSENT":
            if self.pitcher_id is not None or self.pitcher_name is not None:
                raise EvidenceError("ABSENT starter cannot carry pitcher identity")
        else:
            _positive(self.pitcher_id, "pitcher_id")
            _nonempty(self.pitcher_name, "pitcher_name")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OfficialMLBLineupEvidence:
    evidence_id: str
    mlb_game_pk: int
    side: str
    lineup_state: str
    batting_order_ids: tuple[int, ...]
    confirmation_state: str
    source_observed_at: str
    retrieved_at: str
    scheduled_first_pitch: str
    requested_timecode: str | None
    source_payload_ref: str
    source_payload_checksum: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        _nonempty(self.evidence_id, "evidence_id")
        _nonempty(self.schema_version, "schema_version")
        _validate_common(
            mlb_game_pk=self.mlb_game_pk,
            side=self.side,
            source_observed_at=self.source_observed_at,
            retrieved_at=self.retrieved_at,
            scheduled_first_pitch=self.scheduled_first_pitch,
            source_payload_ref=self.source_payload_ref,
            source_payload_checksum=self.source_payload_checksum,
        )
        if self.lineup_state not in {"ABSENT", "PARTIAL", "POPULATED"}:
            raise EvidenceError("lineup_state is unsupported")
        if self.confirmation_state != "NOT_ASSERTED":
            raise EvidenceError(
                "lineup confirmation must not be inferred from feed presence"
            )
        ids = tuple(
            _positive(value, "batting_order_id") for value in self.batting_order_ids
        )
        if len(ids) != len(set(ids)):
            raise EvidenceError("batting order cannot contain duplicate player IDs")
        if self.lineup_state == "ABSENT" and ids:
            raise EvidenceError("ABSENT lineup must have no batting-order IDs")
        if self.lineup_state == "PARTIAL" and not 1 <= len(ids) < 9:
            raise EvidenceError("PARTIAL lineup must contain 1-8 player IDs")
        if self.lineup_state == "POPULATED" and len(ids) < 9:
            raise EvidenceError("POPULATED lineup must contain at least 9 player IDs")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["batting_order_ids"] = list(self.batting_order_ids)
        return result


def _lineup_state(ids: tuple[int, ...]) -> str:
    if not ids:
        return "ABSENT"
    if len(ids) < 9:
        return "PARTIAL"
    return "POPULATED"


def _evidence_id(
    snapshot: OfficialMLBPregameSnapshot,
    *,
    component: str,
    side: str,
) -> str:
    identity = {
        "component": component,
        "side": side,
        "mlb_game_pk": snapshot.mlb_game_pk,
        "source_observed_at": snapshot.source_observed_at,
        "source_payload_checksum": snapshot.source_payload_checksum,
    }
    return str(
        uuid.uuid5(
            _COMPONENT_NAMESPACE,
            json.dumps(identity, sort_keys=True, separators=(",", ":")),
        )
    )


def build_pregame_components(
    snapshot: OfficialMLBPregameSnapshot,
) -> tuple[
    tuple[OfficialMLBStarterEvidence, OfficialMLBStarterEvidence],
    tuple[OfficialMLBLineupEvidence, OfficialMLBLineupEvidence],
]:
    """Split one archived feed snapshot into explicit starter/lineup facts."""

    common = {
        "mlb_game_pk": snapshot.mlb_game_pk,
        "source_observed_at": snapshot.source_observed_at,
        "retrieved_at": snapshot.retrieved_at,
        "scheduled_first_pitch": snapshot.scheduled_first_pitch,
        "requested_timecode": snapshot.requested_timecode,
        "source_payload_ref": snapshot.source_payload_ref,
        "source_payload_checksum": snapshot.source_payload_checksum,
    }

    starters: list[OfficialMLBStarterEvidence] = []
    lineups: list[OfficialMLBLineupEvidence] = []
    for side in ("AWAY", "HOME"):
        prefix = side.casefold()
        pitcher_id = getattr(snapshot, f"{prefix}_probable_pitcher_id")
        pitcher_name = getattr(snapshot, f"{prefix}_probable_pitcher_name")
        starters.append(
            OfficialMLBStarterEvidence(
                evidence_id=_evidence_id(snapshot, component="STARTER", side=side),
                side=side,
                starter_state="PROBABLE" if pitcher_id is not None else "ABSENT",
                pitcher_id=pitcher_id,
                pitcher_name=pitcher_name,
                **common,
            )
        )

        order = tuple(getattr(snapshot, f"{prefix}_batting_order_ids"))
        lineups.append(
            OfficialMLBLineupEvidence(
                evidence_id=_evidence_id(snapshot, component="LINEUP", side=side),
                side=side,
                lineup_state=_lineup_state(order),
                batting_order_ids=order,
                confirmation_state="NOT_ASSERTED",
                **common,
            )
        )

    return (starters[0], starters[1]), (lineups[0], lineups[1])


def canonical_component_json(
    record: OfficialMLBStarterEvidence | OfficialMLBLineupEvidence,
) -> str:
    return json.dumps(
        record.to_dict(),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
