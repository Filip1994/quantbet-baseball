"""Immutable evidence for successful provider odds poll attempts."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from .evidence import EvidenceError
from .raw_archive import ArchiveReceipt

_PROVIDER = "api-sports-baseball"


def _timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{field} must be timezone-aware")
    return parsed


def _nonnegative(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvidenceError(f"{field} must be a non-negative integer")
    return value


@dataclass(frozen=True, slots=True)
class OddsPollAttempt:
    poll_attempt_id: str
    game_id: str
    provider: str
    provider_game_id: int
    attempted_at: str
    kickoff_at: str
    response_rows: int
    raw_market_rows: int
    canonical_rows: int
    source_payload_ref: str
    source_payload_checksum: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field in (
            "poll_attempt_id",
            "game_id",
            "provider",
            "source_payload_ref",
            "source_payload_checksum",
            "schema_version",
        ):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise EvidenceError(f"{field} must be non-empty")
        if self.provider != _PROVIDER:
            raise EvidenceError("odds poll provider is unsupported")
        if (
            isinstance(self.provider_game_id, bool)
            or not isinstance(self.provider_game_id, int)
            or self.provider_game_id <= 0
        ):
            raise EvidenceError("provider_game_id must be a positive integer")
        attempted = _timestamp(self.attempted_at, "attempted_at")
        kickoff = _timestamp(self.kickoff_at, "kickoff_at")
        if attempted >= kickoff:
            raise EvidenceError("odds poll attempt must precede kickoff")
        for field in ("response_rows", "raw_market_rows", "canonical_rows"):
            _nonnegative(getattr(self, field), field)
        checksum = self.source_payload_checksum
        if len(checksum) != 64 or any(
            ch not in "0123456789abcdefABCDEF" for ch in checksum
        ):
            raise EvidenceError("source_payload_checksum must be a SHA-256 hex digest")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_odds_poll_attempt(
    *,
    game_id: int,
    kickoff_at: datetime,
    receipt: ArchiveReceipt,
    response_rows: int,
    raw_market_rows: int,
    canonical_rows: int,
) -> OddsPollAttempt:
    identity = (
        f"quantbet-baseball:odds-poll:{_PROVIDER}:{game_id}:"
        f"{receipt.ref}:{receipt.checksum}"
    )
    return OddsPollAttempt(
        poll_attempt_id=str(uuid.uuid5(uuid.NAMESPACE_URL, identity)),
        game_id=str(game_id),
        provider=_PROVIDER,
        provider_game_id=game_id,
        attempted_at=receipt.captured_at,
        kickoff_at=kickoff_at.isoformat(),
        response_rows=response_rows,
        raw_market_rows=raw_market_rows,
        canonical_rows=canonical_rows,
        source_payload_ref=receipt.ref,
        source_payload_checksum=receipt.checksum,
    )


def canonical_odds_poll_attempt_json(record: OddsPollAttempt) -> str:
    return json.dumps(
        record.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
