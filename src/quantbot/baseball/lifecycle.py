from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

STATES = {
    "DISCOVERED",
    "OBSERVING",
    "MODELLED",
    "ELIGIBLE",
    "SIGNAL",
    "PICK",
    "CLOSING",
    "SETTLED",
    "EVALUATED",
    "SKIPPED",
    "BLOCKED",
    "NO_ODDS",
    "API_ERROR",
    "INSUFFICIENT_DATA",
}

TERMINAL_STATES = {"SETTLED", "EVALUATED", "SKIPPED", "BLOCKED", "NO_ODDS", "API_ERROR", "INSUFFICIENT_DATA"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def observation_id(
    game_id: int | str,
    bookmaker: str,
    market: str,
    selection: str,
    captured_at: str,
    odd: Any,
    handicap: Any = None,
) -> str:
    payload = {
        "game_id": str(game_id),
        "bookmaker": _text(bookmaker),
        "market": _text(market),
        "selection": _text(selection),
        "captured_at": _text(captured_at),
        "odd": _text(odd),
        "handicap": _text(handicap),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return digest[:24]


def flatten_market_observations(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert one API snapshot into the canonical evidence stream.

    Every bookmaker/market/selection is preserved independently. This is the
    evidence layer; production qualification must never filter this stream.
    """
    game_id = snapshot.get("game_id")
    captured_at = _text(snapshot.get("captured_at"))
    source = "api-sports-baseball/odds"
    rows: list[dict[str, Any]] = []
    odds = snapshot.get("odds") or {}
    for bookmaker in odds.get("bookmakers") or []:
        bookmaker_name = _text(bookmaker.get("name"))
        for market in bookmaker.get("markets") or []:
            market_name = _text(market.get("name"))
            for value in market.get("values") or []:
                selection = _text(value.get("value"))
                odd = value.get("odd")
                handicap = value.get("handicap")
                if game_id is None or not bookmaker_name or not market_name or not selection or odd is None:
                    continue
                rows.append(
                    {
                        "observation_id": observation_id(game_id, bookmaker_name, market_name, selection, captured_at, odd, handicap),
                        "event_id": str(game_id),
                        "game_id": game_id,
                        "league": snapshot.get("league"),
                        "home": snapshot.get("home"),
                        "away": snapshot.get("away"),
                        "kickoff": snapshot.get("kickoff"),
                        "bookmaker_id": None,
                        "bookmaker_name": bookmaker_name,
                        "market": market_name,
                        "selection": selection,
                        "handicap": handicap,
                        "odds": odd,
                        "captured_at": captured_at,
                        "source": source,
                        "request_reference": f"odds?game={game_id}",
                        "validation_status": "VALID",
                        "reason": None,
                    }
                )
    return rows


def transition(current: str, target: str, reason: str | None = None) -> dict[str, Any]:
    current = current.upper()
    target = target.upper()
    if current not in STATES or target not in STATES:
        raise ValueError(f"Unknown lifecycle state: {current} -> {target}")
    if current in TERMINAL_STATES and current != target:
        raise ValueError(f"Terminal state cannot transition: {current} -> {target}")
    return {
        "from": current,
        "to": target,
        "at": datetime.now(UTC).isoformat(),
        "reason": reason,
    }
