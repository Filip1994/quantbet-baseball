"""Canonical bookmaker execution policy for QuantBet Baseball."""

from __future__ import annotations

from typing import Any


PLAYABLE_BOOKMAKERS = frozenset({"bet365", "1xbet"})


def normalize_bookmaker(value: Any) -> str:
    """Normalize provider bookmaker names without inventing unsupported aliases."""
    return " ".join(str(value or "").strip().casefold().split())


def is_playable_bookmaker(value: Any) -> bool:
    """Return whether the bookmaker is permitted for paper execution."""
    return normalize_bookmaker(value) in PLAYABLE_BOOKMAKERS
