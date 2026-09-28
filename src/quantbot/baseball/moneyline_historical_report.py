"""Read-only CLI/report for historical Moneyline baseline evaluation."""

from __future__ import annotations

import argparse
import json
import math
import os
from collections.abc import Sequence
from typing import Any

import psycopg

from .game_history_repository import PostgreSQLGameHistoryRepository
from .moneyline_historical_evaluation import (
    HistoricalMoneylineExample,
    evaluate_historical_moneyline_from_repository,
)


def calibration_bins(
    examples: Sequence[HistoricalMoneylineExample],
    *,
    bin_count: int = 10,
) -> tuple[dict[str, Any], ...]:
    if bin_count < 2:
        raise ValueError("bin_count must be at least 2")

    groups: list[list[HistoricalMoneylineExample]] = [
        [] for _ in range(bin_count)
    ]
    for row in examples:
        probability = min(max(float(row.home_probability), 0.0), 1.0)
        index = min(bin_count - 1, int(probability * bin_count))
        groups[index].append(row)

    result: list[dict[str, Any]] = []
    for index, rows in enumerate(groups):
        lower = index / bin_count
        upper = (index + 1) / bin_count
        if not rows:
            result.append(
                {
                    "lower": lower,
                    "upper": upper,
                    "count": 0,
                    "mean_probability": None,
                    "observed_home_win_rate": None,
                    "brier_score": None,
                }
            )
            continue
        count = len(rows)
        result.append(
            {
                "lower": lower,
                "upper": upper,
                "count": count,
                "mean_probability": (
                    sum(row.home_probability for row in rows) / count
                ),
                "observed_home_win_rate": (
                    sum(row.target_home_win for row in rows) / count
                ),
                "brier_score": sum(row.brier_loss for row in rows) / count,
            }
        )
    return tuple(result)


def build_historical_report(
    repository,
    *,
    league_id: int,
    season: int,
    shrinkage_games: float = 30.0,
    min_overall_games: int = 10,
    min_context_games: int = 5,
    bin_count: int = 10,
) -> dict[str, Any]:
    evaluation, examples = evaluate_historical_moneyline_from_repository(
        repository,
        league_id=league_id,
        season=season,
        shrinkage_games=shrinkage_games,
        min_overall_games=min_overall_games,
        min_context_games=min_context_games,
    )

    probabilities = [row.home_probability for row in examples]
    home_wins = [row.target_home_win for row in examples]
    distribution = {
        "minimum_home_probability": min(probabilities) if probabilities else None,
        "maximum_home_probability": max(probabilities) if probabilities else None,
        "mean_home_probability": (
            sum(probabilities) / len(probabilities) if probabilities else None
        ),
        "observed_home_win_rate": (
            sum(home_wins) / len(home_wins) if home_wins else None
        ),
    }
    if probabilities and not all(math.isfinite(value) for value in probabilities):
        raise ValueError("historical report contains non-finite probabilities")

    return {
        "evaluation": evaluation.to_dict(),
        "probability_distribution": distribution,
        "calibration_bins": calibration_bins(examples, bin_count=bin_count),
        "first_example_first_pitch": (
            examples[0].scheduled_first_pitch if examples else None
        ),
        "last_example_first_pitch": (
            examples[-1].scheduled_first_pitch if examples else None
        ),
    }


def run_report(
    *,
    database_url: str,
    league_id: int,
    season: int,
    shrinkage_games: float,
    min_overall_games: int,
    min_context_games: int,
    bin_count: int,
) -> dict[str, Any]:
    with psycopg.connect(database_url) as connection:
        repository = PostgreSQLGameHistoryRepository(connection)
        return build_historical_report(
            repository,
            league_id=league_id,
            season=season,
            shrinkage_games=shrinkage_games,
            min_overall_games=min_overall_games,
            min_context_games=min_context_games,
            bin_count=bin_count,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run read-only historical Moneyline baseline evaluation.",
    )
    parser.add_argument("--league-id", type=int, default=1)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--shrinkage-games", type=float, default=30.0)
    parser.add_argument("--min-overall-games", type=int, default=10)
    parser.add_argument("--min-context-games", type=int, default=5)
    parser.add_argument("--bin-count", type=int, default=10)
    return parser


def main() -> None:
    args = _parser().parse_args()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    report = run_report(
        database_url=database_url,
        league_id=args.league_id,
        season=args.season,
        shrinkage_games=args.shrinkage_games,
        min_overall_games=args.min_overall_games,
        min_context_games=args.min_context_games,
        bin_count=args.bin_count,
    )
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
