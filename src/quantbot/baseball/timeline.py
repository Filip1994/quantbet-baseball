"""Deterministic reconstruction of pre-game odds timelines.

The timeline layer consumes validated immutable ``OddsObservation`` records. It
never invents prices: opening and closing values are selected only from observed
records, and line changes create separate market epochs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from .evidence import EvidenceError, OddsObservation


@dataclass(frozen=True)
class MarketEpoch:
    market_family: str
    line: float | None
    observations: tuple[OddsObservation, ...]

    @property
    def first_observed_at(self) -> str:
        return self.observations[0].observed_at

    @property
    def last_observed_at(self) -> str:
        return self.observations[-1].observed_at

    def observations_for(self, selection: str, bookmaker: str | None = None) -> tuple[OddsObservation, ...]:
        values = tuple(o for o in self.observations if o.selection == selection)
        if bookmaker is not None:
            values = tuple(o for o in values if o.bookmaker == bookmaker)
        return values


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError("timeline timestamps must be timezone-aware")
    return parsed


def reconstruct_epochs(observations: Iterable[OddsObservation]) -> tuple[MarketEpoch, ...]:
    """Group observations by exact market identity and line, then sort deterministically.

    A line change is represented by a separate epoch. Exact duplicate records are
    collapsed by observation ID only when their canonical content is identical;
    conflicting IDs or duplicate bookmaker/selection prices are rejected.
    """
    records = tuple(observations)
    if not records:
        return ()
    game_ids = {o.game_id for o in records}
    kickoffs = {o.kickoff_at for o in records}
    if len(game_ids) != 1 or len(kickoffs) != 1:
        raise EvidenceError("timeline requires one game_id and one kickoff_at")

    by_id: dict[str, OddsObservation] = {}
    for record in records:
        prior = by_id.get(record.observation_id)
        if prior is not None and prior != record:
            raise EvidenceError("conflicting observation_id in timeline")
        by_id[record.observation_id] = record

    unique = sorted(by_id.values(), key=lambda o: (_instant(o.observed_at), o.observation_id))
    seen_quote: dict[tuple[str, str, str, float | None], OddsObservation] = {}
    for record in unique:
        key = (record.market_family, record.selection, record.bookmaker, record.line)
        prior = seen_quote.get(key)
        if prior is not None and prior.observed_at == record.observed_at and prior.decimal_odds != record.decimal_odds:
            raise EvidenceError("conflicting same-time bookmaker/selection quote")
        seen_quote[key] = record

    grouped: dict[tuple[str, float | None], list[OddsObservation]] = {}
    for record in unique:
        grouped.setdefault((record.market_family, record.line), []).append(record)

    return tuple(
        MarketEpoch(family, line, tuple(values))
        for (family, line), values in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1] is not None, item[0][1] or 0.0))
    )


def select_observed_price(epoch: MarketEpoch, selection: str, at: str) -> OddsObservation | None:
    """Select the latest observed quote at or before ``at``; return None if absent."""
    cutoff = _instant(at)
    candidates = [o for o in epoch.observations_for(selection) if _instant(o.observed_at) <= cutoff]
    return max(candidates, key=lambda o: (_instant(o.observed_at), o.observation_id), default=None)


def opening_observation(epoch: MarketEpoch, selection: str) -> OddsObservation | None:
    return min(epoch.observations_for(selection), key=lambda o: (_instant(o.observed_at), o.observation_id), default=None)


def closing_observation(epoch: MarketEpoch, selection: str) -> OddsObservation | None:
    return max(epoch.observations_for(selection), key=lambda o: (_instant(o.observed_at), o.observation_id), default=None)
