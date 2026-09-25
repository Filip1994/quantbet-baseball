"""Map durable API snapshots into canonical PostgreSQL evidence."""

from __future__ import annotations

import json
import math
import uuid
from datetime import datetime
from typing import Any

from .evidence import OddsObservation
from .raw_archive import ArchiveReceipt

_MONEYLINE_MARKETS = {
    "moneyline",
    "home/away",
    "match winner",
    "game winner",
    "match result",
    "game result",
}
_OBSERVATION_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/odds-observation/v1",
)


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().replace("_", " ").split())


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _decimal_odds(value: Any) -> float | None:
    try:
        odds = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(odds) or odds <= 1.0:
        return None
    return odds


def _selection_side(
    value: Any,
    *,
    home: str,
    away: str,
) -> str | None:
    normalized = _norm(value)
    if normalized in {"home", "1"} or normalized == _norm(home):
        return "home"
    if normalized in {"away", "2"} or normalized == _norm(away):
        return "away"
    return None


def _observation_uuid(identity: dict[str, Any]) -> str:
    canonical = json.dumps(
        identity,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return str(uuid.uuid5(_OBSERVATION_NAMESPACE, canonical))


def canonical_moneyline_observations(
    snapshot: dict[str, Any],
    receipt: ArchiveReceipt,
) -> tuple[OddsObservation, ...]:
    """Return strict pregame, full-game moneyline evidence only."""

    game_id = snapshot.get("game_id")
    kickoff_at = str(snapshot.get("kickoff") or "").strip()
    home = str(snapshot.get("home") or "").strip()
    away = str(snapshot.get("away") or "").strip()
    observed = _parse_timestamp(receipt.captured_at)
    kickoff = _parse_timestamp(kickoff_at)

    if (
        game_id is None
        or not kickoff_at
        or not home
        or not away
        or observed is None
        or kickoff is None
        or observed >= kickoff
    ):
        return ()

    rows: dict[str, OddsObservation] = {}
    odds = snapshot.get("odds") or {}
    for bookmaker in odds.get("bookmakers") or []:
        if not isinstance(bookmaker, dict):
            continue
        bookmaker_name = str(bookmaker.get("name") or "").strip()
        if not bookmaker_name:
            continue

        for market in bookmaker.get("markets") or []:
            if not isinstance(market, dict):
                continue
            market_name = str(market.get("name") or "").strip()
            if _norm(market_name) not in _MONEYLINE_MARKETS:
                continue

            market_values = market.get("values") or []
            if not isinstance(market_values, list):
                continue
            mapped_sides = [
                _selection_side(
                    value.get("value"),
                    home=home,
                    away=away,
                )
                if isinstance(value, dict)
                else None
                for value in market_values
            ]
            if any(side is None for side in mapped_sides):
                continue

            for value, side in zip(market_values, mapped_sides, strict=True):
                assert isinstance(value, dict)
                assert side is not None
                price = _decimal_odds(value.get("odd"))
                if price is None:
                    continue

                raw_price = str(value.get("odd")).strip()
                identity = {
                    "game_id": str(game_id),
                    "bookmaker": bookmaker_name,
                    "market_family": "moneyline",
                    "market_name": market_name,
                    "selection": side,
                    "decimal_odds": price,
                    "observed_at": receipt.captured_at,
                    "source_payload_checksum": receipt.checksum,
                }
                observation_id = _observation_uuid(identity)
                rows[observation_id] = OddsObservation(
                    observation_id=observation_id,
                    game_id=str(game_id),
                    market_family="moneyline",
                    line=None,
                    selection=side,
                    bookmaker=bookmaker_name,
                    decimal_odds=price,
                    raw_price=raw_price,
                    observed_at=receipt.captured_at,
                    retrieved_at=receipt.captured_at,
                    source_payload_ref=receipt.ref,
                    source_payload_checksum=receipt.checksum,
                    schema_version="1.0",
                    market_status="open",
                    kickoff_at=kickoff_at,
                )

    return tuple(rows[key] for key in sorted(rows))
