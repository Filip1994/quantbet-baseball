"""Canonical bookmaker policy for QuantBet Baseball."""

from __future__ import annotations

from typing import Final

PLAYABLE_BOOKMAKERS: Final[dict[int, str]] = {
    1: "1xbet",
    2: "Bet365",
}


def normalize_bookmaker_name(value: str) -> str:
    return "".join(str(value or "").strip().casefold().split())


def canonical_playable_bookmaker(value: str) -> str | None:
    normalized = normalize_bookmaker_name(value)
    if normalized == "1xbet":
        return "1xbet"
    if normalized == "bet365":
        return "Bet365"
    return None


def is_playable_bookmaker(value: str) -> bool:
    return canonical_playable_bookmaker(value) is not None
