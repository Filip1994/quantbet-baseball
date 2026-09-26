"""Canonical bookmaker execution policy for QuantBet Baseball."""

PLAYABLE_BOOKMAKERS = frozenset({"bet365", "1xbet"})


def normalize_bookmaker(value: object) -> str:
    """Normalize provider bookmaker names without inventing unsupported aliases."""
    return " ".join(str(value or "").strip().casefold().split())


def is_playable_bookmaker(value: object) -> bool:
    """Return whether the bookmaker is permitted for paper execution."""
    return normalize_bookmaker(value) in PLAYABLE_BOOKMAKERS
