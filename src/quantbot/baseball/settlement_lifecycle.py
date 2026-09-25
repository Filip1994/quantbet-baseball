"""Authoritative result, settlement and CLV facts for Baseball moneyline."""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from .decision_lifecycle import RegisteredPick
from .evidence import EvidenceError, OddsObservation
from .fixture_evidence import FixtureObservation
from .market import devig_two_way
from .monitoring_lifecycle import ClosingFinalization
from .raw_archive import ArchiveReceipt

_RESULT_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/game-result-fact/v1",
)
_SETTLEMENT_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/pick-settlement/v1",
)
_TERMINAL_STATUSES = {
    "ft",
    "finished",
    "final",
    "aot",
    "after overtime",
}


def _timestamp(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise EvidenceError(f"{field} must be a non-empty ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise EvidenceError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{field} must be timezone-aware")
    return parsed


def _uuid(namespace: uuid.UUID, identity: dict[str, Any]) -> str:
    canonical = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return str(uuid.uuid5(namespace, canonical))


def _normalise_status(value: str) -> str:
    return " ".join(value.strip().casefold().replace("_", " ").split())


def _score_value(value: Any) -> int | None:
    if isinstance(value, dict):
        for key in ("total", "runs", "score", "points"):
            if key in value:
                return _score_value(value[key])
        return None
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _scores(game: dict[str, Any]) -> tuple[int, int] | None:
    nested = game.get("game")
    nested = nested if isinstance(nested, dict) else {}
    scores = game.get("scores") or nested.get("scores")
    if not isinstance(scores, dict):
        return None
    home = _score_value(scores.get("home"))
    away = _score_value(scores.get("away"))
    if home is None or away is None:
        return None
    return home, away


@dataclass(frozen=True, slots=True)
class GameResultFact:
    result_id: str
    game_id: str
    fixture_observation_id: str
    provider_status: str
    observed_at: str
    home_score: int
    away_score: int
    winner: str
    source_payload_ref: str
    source_payload_checksum: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        for field in (
            "result_id",
            "game_id",
            "fixture_observation_id",
            "provider_status",
            "source_payload_ref",
            "source_payload_checksum",
            "schema_version",
        ):
            if not str(getattr(self, field) or "").strip():
                raise EvidenceError(f"{field} must be non-empty")
        _timestamp(self.observed_at, "observed_at")
        if _normalise_status(self.provider_status) not in _TERMINAL_STATUSES:
            raise EvidenceError("result fact requires a terminal provider status")
        if (
            isinstance(self.home_score, bool)
            or isinstance(self.away_score, bool)
            or self.home_score < 0
            or self.away_score < 0
        ):
            raise EvidenceError("result scores must be non-negative integers")
        expected = (
            "home"
            if self.home_score > self.away_score
            else "away"
            if self.away_score > self.home_score
            else "tie"
        )
        if self.winner != expected:
            raise EvidenceError("winner does not match final score")


@dataclass(frozen=True, slots=True)
class PickSettlement:
    settlement_id: str
    pick_id: str
    game_id: str
    result_id: str
    closing_finalization_id: str
    selection: str
    entry_odds: float
    settled_at: str
    outcome: str
    profit_per_unit: float
    paper_stake_rsd: int
    paper_profit_rsd: float
    closing_outcome: str
    closing_observation_id: str | None
    closing_odds: float | None
    closing_market_probability: float | None
    clv_probability_delta: float | None
    clv_price_ratio: float | None
    clv_status: str
    schema_version: str = "1.1"

    def __post_init__(self) -> None:
        for field in (
            "settlement_id",
            "pick_id",
            "game_id",
            "result_id",
            "closing_finalization_id",
            "schema_version",
        ):
            if not str(getattr(self, field) or "").strip():
                raise EvidenceError(f"{field} must be non-empty")
        if self.selection not in {"home", "away"}:
            raise EvidenceError("settlement selection is unsupported")
        if not math.isfinite(self.entry_odds) or self.entry_odds <= 1.0:
            raise EvidenceError("entry_odds must be greater than 1")
        _timestamp(self.settled_at, "settled_at")
        if self.outcome not in {"WIN", "LOSS", "PUSH"}:
            raise EvidenceError("settlement outcome is unsupported")
        expected_profit = (
            self.entry_odds - 1.0
            if self.outcome == "WIN"
            else -1.0
            if self.outcome == "LOSS"
            else 0.0
        )
        if not math.isclose(
            self.profit_per_unit,
            expected_profit,
            rel_tol=0.0,
            abs_tol=1e-10,
        ):
            raise EvidenceError("profit_per_unit does not match settlement outcome")
        if (
            isinstance(self.paper_stake_rsd, bool)
            or not isinstance(self.paper_stake_rsd, int)
            or self.paper_stake_rsd <= 0
        ):
            raise EvidenceError("paper_stake_rsd must be a positive integer")
        expected_paper_profit = round(expected_profit * self.paper_stake_rsd, 2)
        if not math.isclose(
            self.paper_profit_rsd,
            expected_paper_profit,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise EvidenceError("paper_profit_rsd does not match paper stake and outcome")
        if self.closing_outcome not in {
            "CAPTURED",
            "STALE_QUOTE",
            "NO_VALID_QUOTE",
        }:
            raise EvidenceError("closing outcome is unsupported")

        available = self.clv_status == "AVAILABLE"
        values = (
            self.closing_observation_id,
            self.closing_odds,
            self.closing_market_probability,
            self.clv_probability_delta,
            self.clv_price_ratio,
        )
        if available:
            if self.closing_outcome != "CAPTURED" or any(
                value is None for value in values
            ):
                raise EvidenceError("AVAILABLE CLV requires captured closing evidence")
            assert self.closing_odds is not None
            assert self.closing_market_probability is not None
            if self.closing_odds <= 1.0:
                raise EvidenceError("closing odds must be greater than 1")
            if not 0.0 < self.closing_market_probability < 1.0:
                raise EvidenceError("closing market probability is invalid")
        else:
            expected_status = {
                "STALE_QUOTE": "UNAVAILABLE_STALE_QUOTE",
                "NO_VALID_QUOTE": "UNAVAILABLE_NO_VALID_QUOTE",
            }.get(self.closing_outcome)
            if self.clv_status != expected_status or any(
                value is not None for value in values
            ):
                raise EvidenceError("unavailable CLV shape is invalid")


def canonical_result_json(record: GameResultFact) -> str:
    return json.dumps(
        asdict(record),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def canonical_settlement_json(record: PickSettlement) -> str:
    return json.dumps(
        asdict(record),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def build_game_result_fact(
    game: dict[str, Any],
    fixture: FixtureObservation,
    receipt: ArchiveReceipt,
) -> GameResultFact | None:
    """Return a final result fact only when the provider row is terminal and scored."""

    if fixture.source_payload_ref != receipt.ref:
        raise EvidenceError("fixture and result receipt provenance mismatch")
    if fixture.source_payload_checksum != receipt.checksum:
        raise EvidenceError("fixture and result checksum mismatch")
    if _normalise_status(fixture.provider_status) not in _TERMINAL_STATUSES:
        return None
    scores = _scores(game)
    if scores is None:
        return None
    home_score, away_score = scores
    winner = (
        "home"
        if home_score > away_score
        else "away"
        if away_score > home_score
        else "tie"
    )
    identity = {
        "game_id": fixture.game_id,
        "fixture_observation_id": fixture.fixture_observation_id,
        "provider_status": fixture.provider_status,
        "observed_at": receipt.captured_at,
        "home_score": home_score,
        "away_score": away_score,
        "winner": winner,
        "source_payload_checksum": receipt.checksum,
    }
    return GameResultFact(
        result_id=_uuid(_RESULT_NAMESPACE, identity),
        game_id=fixture.game_id,
        fixture_observation_id=fixture.fixture_observation_id,
        provider_status=fixture.provider_status,
        observed_at=receipt.captured_at,
        home_score=home_score,
        away_score=away_score,
        winner=winner,
        source_payload_ref=receipt.ref,
        source_payload_checksum=receipt.checksum,
    )


def build_pick_settlement(
    pick: RegisteredPick,
    result: GameResultFact,
    closing: ClosingFinalization,
    *,
    settled_at: str,
    closing_pair: tuple[OddsObservation, OddsObservation] | None,
) -> PickSettlement:
    if result.game_id != pick.game_id or closing.game_id != pick.game_id:
        raise EvidenceError("settlement game provenance mismatch")
    if closing.pick_id != pick.pick_id:
        raise EvidenceError("closing finalization does not belong to pick")
    if _timestamp(settled_at, "settled_at") < _timestamp(
        result.observed_at,
        "result.observed_at",
    ):
        raise EvidenceError("settlement cannot predate result evidence")

    if result.winner == "tie":
        outcome = "PUSH"
    elif result.winner == pick.selection:
        outcome = "WIN"
    else:
        outcome = "LOSS"
    profit = (
        pick.entry_odds - 1.0
        if outcome == "WIN"
        else -1.0
        if outcome == "LOSS"
        else 0.0
    )

    closing_observation_id: str | None = None
    closing_odds: float | None = None
    closing_market_probability: float | None = None
    clv_probability_delta: float | None = None
    clv_price_ratio: float | None = None

    if closing.outcome == "CAPTURED":
        if closing_pair is None:
            raise EvidenceError("captured closing requires exact closing pair")
        home, away = closing_pair
        if (
            home.observation_id != closing.candidate_home_observation_id
            or away.observation_id != closing.candidate_away_observation_id
            or home.game_id != pick.game_id
            or away.game_id != pick.game_id
            or home.bookmaker != pick.bookmaker
            or away.bookmaker != pick.bookmaker
        ):
            raise EvidenceError("closing pair provenance mismatch")
        de_vigged = devig_two_way(1.0 / home.decimal_odds, 1.0 / away.decimal_odds)
        if de_vigged is None:
            raise EvidenceError("closing pair cannot be de-vigged")
        selected = home if pick.selection == "home" else away
        if selected.observation_id != closing.closing_observation_id:
            raise EvidenceError("selected closing observation mismatch")
        closing_observation_id = selected.observation_id
        closing_odds = selected.decimal_odds
        closing_market_probability = (
            de_vigged[0] if pick.selection == "home" else de_vigged[1]
        )
        clv_probability_delta = closing_market_probability - pick.market_probability
        clv_price_ratio = pick.entry_odds / closing_odds - 1.0
        clv_status = "AVAILABLE"
    elif closing.outcome == "STALE_QUOTE":
        if closing_pair is not None:
            raise EvidenceError("stale close must not produce CLV")
        clv_status = "UNAVAILABLE_STALE_QUOTE"
    else:
        if closing_pair is not None:
            raise EvidenceError("missing close must not produce CLV")
        clv_status = "UNAVAILABLE_NO_VALID_QUOTE"

    identity = {
        "pick_id": pick.pick_id,
        "result_id": result.result_id,
        "closing_finalization_id": closing.finalization_id,
    }
    return PickSettlement(
        settlement_id=_uuid(_SETTLEMENT_NAMESPACE, identity),
        pick_id=pick.pick_id,
        game_id=pick.game_id,
        result_id=result.result_id,
        closing_finalization_id=closing.finalization_id,
        selection=pick.selection,
        entry_odds=pick.entry_odds,
        settled_at=settled_at,
        outcome=outcome,
        profit_per_unit=profit,
        paper_stake_rsd=pick.paper_stake_rsd,
        paper_profit_rsd=round(profit * pick.paper_stake_rsd, 2),
        closing_outcome=closing.outcome,
        closing_observation_id=closing_observation_id,
        closing_odds=closing_odds,
        closing_market_probability=closing_market_probability,
        clv_probability_delta=clv_probability_delta,
        clv_price_ratio=clv_price_ratio,
        clv_status=clv_status,
    )
