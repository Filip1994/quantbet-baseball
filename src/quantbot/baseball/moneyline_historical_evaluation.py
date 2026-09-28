"""Chronological research evaluation for the Moneyline team-strength baseline.

This module uses EVENT_TIME_RECONSTRUCTION. Historical raw evidence may have
been retrieved after the target game, so these rows are not claims about what
the production system knew live. Leakage is controlled by event ordering:
only completed games whose scheduled first pitch precedes the target game may
contribute to that target's team-strength rates.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Iterable, Protocol

from .evidence import EvidenceError
from .game_history import GameHistorySnapshot
from .moneyline_baseline import (
    MODEL_VERSION,
    TeamStrengthRates,
    calculate_team_strength_probability,
)

EVALUATION_MODE = "EVENT_TIME_RECONSTRUCTION"


def _timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def _latest_by_game(
    snapshots: Iterable[GameHistorySnapshot],
) -> dict[int, GameHistorySnapshot]:
    latest: dict[int, GameHistorySnapshot] = {}
    for row in snapshots:
        existing = latest.get(row.provider_game_id)
        if existing is None or _timestamp(row.observed_at, "observed_at") > _timestamp(
            existing.observed_at,
            "existing.observed_at",
        ):
            latest[row.provider_game_id] = row
    return latest


def _is_usable_final(row: GameHistorySnapshot) -> bool:
    return (
        row.is_final
        and row.home_score is not None
        and row.away_score is not None
        and row.home_score != row.away_score
    )


@dataclass(frozen=True, slots=True)
class ReconstructedTeamRates:
    team_id: int
    overall_games: int
    context_games: int
    wins: int
    context_wins: int
    runs_for: int
    runs_against: int
    context_runs_for: int
    context_runs_against: int
    context_site: str

    @property
    def overall_win_pct(self) -> float:
        return self.wins / self.overall_games

    @property
    def context_win_pct(self) -> float:
        return self.context_wins / self.context_games

    @property
    def overall_runs_per_game(self) -> float:
        return self.runs_for / self.overall_games

    @property
    def overall_runs_allowed_per_game(self) -> float:
        return self.runs_against / self.overall_games

    @property
    def context_runs_per_game(self) -> float:
        return self.context_runs_for / self.context_games

    @property
    def context_runs_allowed_per_game(self) -> float:
        return self.context_runs_against / self.context_games


def reconstruct_team_rates(
    *,
    target: GameHistorySnapshot,
    team_id: int,
    context_site: str,
    history: Iterable[GameHistorySnapshot],
    min_overall_games: int,
    min_context_games: int,
) -> ReconstructedTeamRates | None:
    """Reconstruct rates from completed prior events only."""

    if context_site not in {"HOME", "AWAY"}:
        raise ValueError("context_site must be HOME or AWAY")
    if min_overall_games < 1 or min_context_games < 1:
        raise ValueError("minimum game thresholds must be positive")
    if team_id not in {target.home_team_id, target.away_team_id}:
        raise EvidenceError("team_id is not part of target game")

    target_start = _timestamp(target.scheduled_first_pitch, "target.first_pitch")
    latest = _latest_by_game(history)

    overall_games = 0
    context_games = 0
    wins = 0
    context_wins = 0
    runs_for = 0
    runs_against = 0
    context_runs_for = 0
    context_runs_against = 0

    for row in latest.values():
        if row.provider_game_id == target.provider_game_id:
            continue
        if row.league_id != target.league_id or row.season != target.season:
            continue
        if _timestamp(row.scheduled_first_pitch, "history.first_pitch") >= target_start:
            continue
        if not _is_usable_final(row):
            continue

        if row.home_team_id == team_id:
            site = "HOME"
            scored = int(row.home_score)
            allowed = int(row.away_score)
        elif row.away_team_id == team_id:
            site = "AWAY"
            scored = int(row.away_score)
            allowed = int(row.home_score)
        else:
            continue

        won = scored > allowed
        overall_games += 1
        wins += int(won)
        runs_for += scored
        runs_against += allowed

        if site == context_site:
            context_games += 1
            context_wins += int(won)
            context_runs_for += scored
            context_runs_against += allowed

    if overall_games < min_overall_games or context_games < min_context_games:
        return None
    if runs_for <= 0 or runs_against <= 0:
        return None
    if context_runs_for <= 0 or context_runs_against <= 0:
        return None

    return ReconstructedTeamRates(
        team_id=team_id,
        overall_games=overall_games,
        context_games=context_games,
        wins=wins,
        context_wins=context_wins,
        runs_for=runs_for,
        runs_against=runs_against,
        context_runs_for=context_runs_for,
        context_runs_against=context_runs_against,
        context_site=context_site,
    )


@dataclass(frozen=True, slots=True)
class HistoricalMoneylineExample:
    provider_game_id: int
    scheduled_first_pitch: str
    home_team_id: int
    away_team_id: int
    model_version: str
    evaluation_mode: str
    home_probability: float
    away_probability: float
    home_expected_runs: float
    away_expected_runs: float
    home_overall_games: int
    home_context_games: int
    away_overall_games: int
    away_context_games: int
    target_home_win: int
    brier_loss: float
    log_loss: float
    correct: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def reconstruct_historical_example(
    target: GameHistorySnapshot,
    history: Iterable[GameHistorySnapshot],
    *,
    shrinkage_games: float = 30.0,
    min_overall_games: int = 10,
    min_context_games: int = 5,
) -> HistoricalMoneylineExample | None:
    """Project first, then attach the target result strictly as the label."""

    if not _is_usable_final(target):
        return None

    home = reconstruct_team_rates(
        target=target,
        team_id=target.home_team_id,
        context_site="HOME",
        history=history,
        min_overall_games=min_overall_games,
        min_context_games=min_context_games,
    )
    away = reconstruct_team_rates(
        target=target,
        team_id=target.away_team_id,
        context_site="AWAY",
        history=history,
        min_overall_games=min_overall_games,
        min_context_games=min_context_games,
    )
    if home is None or away is None:
        return None

    core = calculate_team_strength_probability(
        TeamStrengthRates(
            home_overall_runs_per_game=home.overall_runs_per_game,
            home_context_runs_per_game=home.context_runs_per_game,
            home_overall_runs_allowed_per_game=home.overall_runs_allowed_per_game,
            home_context_runs_allowed_per_game=home.context_runs_allowed_per_game,
            home_context_sample_games=home.context_games,
            away_overall_runs_per_game=away.overall_runs_per_game,
            away_context_runs_per_game=away.context_runs_per_game,
            away_overall_runs_allowed_per_game=away.overall_runs_allowed_per_game,
            away_context_runs_allowed_per_game=away.context_runs_allowed_per_game,
            away_context_sample_games=away.context_games,
        ),
        shrinkage_games=shrinkage_games,
    )

    target_home_win = int(int(target.home_score) > int(target.away_score))
    probability = min(max(core.home_probability, 1e-12), 1.0 - 1e-12)
    brier = (probability - target_home_win) ** 2
    log_loss = -(
        target_home_win * math.log(probability)
        + (1 - target_home_win) * math.log(1.0 - probability)
    )
    correct = int((probability >= 0.5) == bool(target_home_win))

    return HistoricalMoneylineExample(
        provider_game_id=target.provider_game_id,
        scheduled_first_pitch=target.scheduled_first_pitch,
        home_team_id=target.home_team_id,
        away_team_id=target.away_team_id,
        model_version=MODEL_VERSION,
        evaluation_mode=EVALUATION_MODE,
        home_probability=core.home_probability,
        away_probability=core.away_probability,
        home_expected_runs=core.home_expected_runs,
        away_expected_runs=core.away_expected_runs,
        home_overall_games=home.overall_games,
        home_context_games=home.context_games,
        away_overall_games=away.overall_games,
        away_context_games=away.context_games,
        target_home_win=target_home_win,
        brier_loss=brier,
        log_loss=log_loss,
        correct=correct,
    )


@dataclass(frozen=True, slots=True)
class HistoricalMoneylineEvaluation:
    model_version: str
    evaluation_mode: str
    games_available: int
    examples: int
    skipped_insufficient_or_invalid: int
    brier_score: float | None
    log_loss: float | None
    accuracy: float | None
    shrinkage_games: float
    min_overall_games: int
    min_context_games: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class HistoricalEvaluationRepository(Protocol):
    def latest_snapshots_for_season(
        self,
        *,
        league_id: int,
        season: int,
    ) -> tuple[GameHistorySnapshot, ...]: ...


def evaluate_historical_moneyline_baseline(
    snapshots: Iterable[GameHistorySnapshot],
    *,
    shrinkage_games: float = 30.0,
    min_overall_games: int = 10,
    min_context_games: int = 5,
) -> tuple[HistoricalMoneylineEvaluation, tuple[HistoricalMoneylineExample, ...]]:
    """Evaluate final games in chronological event-time order."""

    if min_overall_games < 1 or min_context_games < 1:
        raise ValueError("minimum game thresholds must be positive")

    latest = _latest_by_game(snapshots)
    targets = sorted(
        (row for row in latest.values() if _is_usable_final(row)),
        key=lambda row: (
            _timestamp(row.scheduled_first_pitch, "target.first_pitch"),
            row.provider_game_id,
        ),
    )
    all_rows = tuple(latest.values())
    examples: list[HistoricalMoneylineExample] = []
    for target in targets:
        example = reconstruct_historical_example(
            target,
            all_rows,
            shrinkage_games=shrinkage_games,
            min_overall_games=min_overall_games,
            min_context_games=min_context_games,
        )
        if example is not None:
            examples.append(example)

    count = len(examples)
    evaluation = HistoricalMoneylineEvaluation(
        model_version=MODEL_VERSION,
        evaluation_mode=EVALUATION_MODE,
        games_available=len(targets),
        examples=count,
        skipped_insufficient_or_invalid=len(targets) - count,
        brier_score=(
            sum(row.brier_loss for row in examples) / count if count else None
        ),
        log_loss=(
            sum(row.log_loss for row in examples) / count if count else None
        ),
        accuracy=(sum(row.correct for row in examples) / count if count else None),
        shrinkage_games=shrinkage_games,
        min_overall_games=min_overall_games,
        min_context_games=min_context_games,
    )
    return evaluation, tuple(examples)


def evaluate_historical_moneyline_from_repository(
    repository: HistoricalEvaluationRepository,
    *,
    league_id: int,
    season: int,
    shrinkage_games: float = 30.0,
    min_overall_games: int = 10,
    min_context_games: int = 5,
) -> tuple[HistoricalMoneylineEvaluation, tuple[HistoricalMoneylineExample, ...]]:
    """Load one season's canonical research reconstruction and evaluate it."""

    snapshots = repository.latest_snapshots_for_season(
        league_id=league_id,
        season=season,
    )
    return evaluate_historical_moneyline_baseline(
        snapshots,
        shrinkage_games=shrinkage_games,
        min_overall_games=min_overall_games,
        min_context_games=min_context_games,
    )
