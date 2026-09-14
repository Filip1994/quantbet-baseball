from __future__ import annotations

import math
from typing import Any


def _positive_finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0.0:
        return None
    return number


def poisson_moneyline_probabilities(
    home_expected_runs: Any,
    away_expected_runs: Any,
    *,
    max_runs: int = 100,
) -> tuple[float, float] | None:
    """Convert expected runs into two-way win probabilities.

    The model assumes independent Poisson scoring for home and away teams.
    Because regulation ties are not a valid final MLB outcome, the probability
    mass for equal scores is excluded and the remaining two-way mass is
    normalized. Inputs and numerical settings are validated conservatively.
    """
    home_lambda = _positive_finite(home_expected_runs)
    away_lambda = _positive_finite(away_expected_runs)
    if home_lambda is None or away_lambda is None:
        return None
    if not isinstance(max_runs, int) or isinstance(max_runs, bool) or max_runs < 20:
        return None

    home_pmf = [math.exp(-home_lambda)]
    away_pmf = [math.exp(-away_lambda)]
    for _ in range(max_runs):
        home_pmf.append(home_pmf[-1] * home_lambda / len(home_pmf))
        away_pmf.append(away_pmf[-1] * away_lambda / len(away_pmf))

    home_win = 0.0
    away_win = 0.0
    for home_runs, home_probability in enumerate(home_pmf):
        for away_runs, away_probability in enumerate(away_pmf):
            joint = home_probability * away_probability
            if home_runs > away_runs:
                home_win += joint
            elif away_runs > home_runs:
                away_win += joint

    total = home_win + away_win
    if not math.isfinite(total) or total <= 0.0:
        return None
    return home_win / total, away_win / total
