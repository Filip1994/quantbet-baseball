"""Read-only Baseball Moneyline performance analytics."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from html import escape
from math import log, sqrt
from statistics import mean, median
from typing import Any

ANALYTICS_CONTRACT_VERSION = "BASEBALL_MONEYLINE_ANALYTICS_V1"


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        stamp = value
    else:
        try:
            stamp = datetime.fromisoformat(str(value))
        except ValueError:
            return None
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        return stamp.replace(tzinfo=UTC)
    return stamp.astimezone(UTC)


def _mean(values: Sequence[float]) -> float | None:
    return mean(values) if values else None


def _median(values: Sequence[float]) -> float | None:
    return median(values) if values else None


def _pct(value: float | None) -> float | None:
    return None if value is None else value * 100.0


def _sample_band(n: int) -> str:
    if n < 20:
        return "SIGNAL_ONLY"
    if n < 50:
        return "MONITOR"
    if n < 100:
        return "PROVISIONAL_EVIDENCE"
    return "STABILITY_REVIEW"


def _wilson_interval(wins: int, trials: int) -> tuple[float | None, float | None]:
    if trials <= 0:
        return None, None
    z = 1.959963984540054
    observed = wins / trials
    denominator = 1 + (z * z / trials)
    centre = (observed + (z * z / (2 * trials))) / denominator
    margin = (
        z
        * sqrt((observed * (1 - observed) / trials) + (z * z / (4 * trials * trials)))
        / denominator
    )
    return max(0.0, centre - margin), min(1.0, centre + margin)


def _bucket_probability(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "UNKNOWN"
    pct = number * 100
    if pct < 45:
        return "<45%"
    if pct < 50:
        return "45-50%"
    if pct < 55:
        return "50-55%"
    if pct < 60:
        return "55-60%"
    return "60%+"


def _bucket_odds(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "UNKNOWN"
    if number < 1.50:
        return "<1.50"
    if number < 1.80:
        return "1.50-1.79"
    if number < 2.00:
        return "1.80-1.99"
    if number < 2.50:
        return "2.00-2.49"
    return "2.50+"


def _bucket_edge(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "UNKNOWN"
    pct = number * 100
    if pct < 2:
        return "<2pp"
    if pct < 5:
        return "2-5pp"
    if pct < 8:
        return "5-8pp"
    if pct < 12:
        return "8-12pp"
    return "12pp+"


def _bucket_ev(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "UNKNOWN"
    pct = number * 100
    if pct < 3:
        return "<3%"
    if pct < 5:
        return "3-5%"
    if pct < 10:
        return "5-10%"
    if pct < 15:
        return "10-15%"
    return "15%+"


def _bucket_uncertainty(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "UNKNOWN"
    if number < 0.025:
        return "<0.025"
    if number < 0.05:
        return "0.025-0.050"
    if number < 0.10:
        return "0.050-0.100"
    return "0.100+"


def _bucket_t_minus(row: dict[str, Any]) -> str:
    kickoff = _dt(row.get("kickoff_at"))
    registered = _dt(row.get("registered_at"))
    if kickoff is None or registered is None:
        return "UNKNOWN"
    hours = (kickoff - registered).total_seconds() / 3600
    if hours < 1:
        return "<1h"
    if hours < 3:
        return "1-3h"
    if hours < 6:
        return "3-6h"
    return "6h+"


def _favorite_status(row: dict[str, Any]) -> str:
    p = _num(row.get("market_probability"))
    if p is None:
        return "UNKNOWN"
    if abs(p - 0.5) < 1e-9:
        return "PICKEM"
    return "FAVORITE" if p > 0.5 else "UNDERDOG"


def _clv_sign(row: dict[str, Any]) -> str:
    if row.get("clv_status") != "AVAILABLE":
        return "UNAVAILABLE"
    value = _num(row.get("clv_probability_delta"))
    if value is None:
        return "UNAVAILABLE"
    if value > 0:
        return "POSITIVE"
    if value < 0:
        return "NEGATIVE"
    return "FLAT"


def _cohort_metrics(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    settled = [
        row for row in rows if row.get("settlement_outcome") in {"WIN", "LOSS", "PUSH"}
    ]
    graded = [
        row for row in settled if row.get("settlement_outcome") in {"WIN", "LOSS"}
    ]
    wins = sum(row.get("settlement_outcome") == "WIN" for row in graded)
    losses = sum(row.get("settlement_outcome") == "LOSS" for row in graded)
    pushes = sum(row.get("settlement_outcome") == "PUSH" for row in settled)
    graded_n = wins + losses
    observed = wins / graded_n if graded_n else None

    model_ps = [
        value
        for row in graded
        if (value := _num(row.get("model_probability"))) is not None
    ]
    expected = _mean(model_ps)
    calibration_gap = (
        observed - expected if observed is not None and expected is not None else None
    )
    brier_values = []
    log_loss_values = []
    for row in graded:
        p = _num(row.get("model_probability"))
        if p is None:
            continue
        actual = 1.0 if row.get("settlement_outcome") == "WIN" else 0.0
        brier_values.append((p - actual) ** 2)
        clipped = min(max(p, 1e-12), 1 - 1e-12)
        log_loss_values.append(-log(clipped if actual == 1.0 else 1.0 - clipped))

    profit_units = [
        value
        for row in settled
        if (value := _num(row.get("profit_per_unit"))) is not None
    ]
    roi = sum(profit_units) / len(settled) if settled else None
    pnl_minor = sum(int(row.get("paper_profit_minor") or 0) for row in settled)

    entry_odds = [
        value for row in rows if (value := _num(row.get("entry_odds"))) is not None
    ]
    model_all = [
        value
        for row in rows
        if (value := _num(row.get("model_probability"))) is not None
    ]
    market_all = [
        value
        for row in rows
        if (value := _num(row.get("market_probability"))) is not None
    ]
    edges = [value for row in rows if (value := _num(row.get("edge"))) is not None]
    evs = [
        value
        for row in rows
        if (value := _num(row.get("expected_value_per_unit"))) is not None
    ]
    uncertainty = [
        value
        for row in rows
        if (value := _num(row.get("uncertainty_metric"))) is not None
    ]

    clv_values = [
        value
        for row in settled
        if row.get("clv_status") == "AVAILABLE"
        and (value := _num(row.get("clv_probability_delta"))) is not None
    ]
    clv_price_ratios = [
        value
        for row in settled
        if row.get("clv_status") == "AVAILABLE"
        and (value := _num(row.get("clv_price_ratio"))) is not None
    ]

    t_minus_minutes: list[float] = []
    for row in rows:
        kickoff = _dt(row.get("kickoff_at"))
        registered = _dt(row.get("registered_at"))
        if kickoff is not None and registered is not None:
            t_minus_minutes.append((kickoff - registered).total_seconds() / 60)

    prelim_odds_delta = []
    prelim_edge_delta = []
    prelim_ev_delta = []
    final_quote_age = []
    for row in rows:
        final_odds = _num(row.get("entry_odds"))
        prelim_odds = _num(row.get("preliminary_odds"))
        if final_odds is not None and prelim_odds is not None:
            prelim_odds_delta.append(final_odds - prelim_odds)
        final_edge = _num(row.get("edge"))
        prelim_edge = _num(row.get("preliminary_edge"))
        if final_edge is not None and prelim_edge is not None:
            prelim_edge_delta.append(final_edge - prelim_edge)
        final_ev = _num(row.get("expected_value_per_unit"))
        prelim_ev = _num(row.get("preliminary_ev"))
        if final_ev is not None and prelim_ev is not None:
            prelim_ev_delta.append(final_ev - prelim_ev)
        age = _num(row.get("final_quote_age_seconds"))
        if age is not None:
            final_quote_age.append(age)

    win_low, win_high = _wilson_interval(wins, graded_n)
    avg_ev = _mean(evs)
    return {
        "registered_n": len(rows),
        "settled_n": len(settled),
        "pending_n": len(rows) - len(settled),
        "graded_n": graded_n,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "win_rate_pct": _pct(observed),
        "expected_win_rate_pct": _pct(expected),
        "calibration_gap_pp": _pct(calibration_gap),
        "win_rate_wilson_95_low_pct": _pct(win_low),
        "win_rate_wilson_95_high_pct": _pct(win_high),
        "brier_score": _mean(brier_values),
        "log_loss": _mean(log_loss_values),
        "roi_pct": _pct(roi),
        "paper_pnl_minor": pnl_minor,
        "avg_entry_odds": _mean(entry_odds),
        "median_entry_odds": _median(entry_odds),
        "avg_model_probability_pct": _pct(_mean(model_all)),
        "avg_market_probability_pct": _pct(_mean(market_all)),
        "avg_edge_pct": _pct(_mean(edges)),
        "avg_ev_pct": _pct(avg_ev),
        "ev_realization_gap_pp": (
            _pct(roi - avg_ev) if roi is not None and avg_ev is not None else None
        ),
        "avg_uncertainty": _mean(uncertainty),
        "clv_count": len(clv_values),
        "clv_coverage_pct": (len(clv_values) / len(settled) * 100 if settled else None),
        "avg_clv_probability_delta_pct": _pct(_mean(clv_values)),
        "median_clv_probability_delta_pct": _pct(_median(clv_values)),
        "positive_clv_rate_pct": (
            sum(value > 0 for value in clv_values) / len(clv_values) * 100
            if clv_values
            else None
        ),
        "avg_clv_price_ratio": _mean(clv_price_ratios),
        "avg_t_minus_minutes": _mean(t_minus_minutes),
        "avg_prelim_to_final_odds_delta": _mean(prelim_odds_delta),
        "avg_prelim_to_final_edge_delta_pp": _pct(_mean(prelim_edge_delta)),
        "avg_prelim_to_final_ev_delta_pp": _pct(_mean(prelim_ev_delta)),
        "avg_final_quote_age_seconds": _mean(final_quote_age),
        "sample_band": _sample_band(graded_n),
    }


def _cohort_rows(
    rows: Sequence[dict[str, Any]],
    key_name: str,
    key_fn: Callable[[dict[str, Any]], str],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[key_fn(row)].append(row)
    output = []
    for key, cohort in grouped.items():
        output.append({key_name: key, **_cohort_metrics(cohort)})
    return sorted(
        output,
        key=lambda item: (-int(item["registered_n"]), str(item[key_name])),
    )


def _streak_and_drawdown(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    settled = sorted(
        (
            row
            for row in rows
            if row.get("settlement_outcome") in {"WIN", "LOSS", "PUSH"}
        ),
        key=lambda row: (
            _dt(row.get("registered_at")) or datetime.min.replace(tzinfo=UTC)
        ),
    )
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    win_streak = loss_streak = max_win_streak = max_loss_streak = 0
    for row in settled:
        profit = _num(row.get("profit_per_unit")) or 0.0
        cumulative += profit
        peak = max(peak, cumulative)
        max_drawdown = min(max_drawdown, cumulative - peak)
        outcome = row.get("settlement_outcome")
        if outcome == "WIN":
            win_streak += 1
            loss_streak = 0
        elif outcome == "LOSS":
            loss_streak += 1
            win_streak = 0
        else:
            win_streak = 0
            loss_streak = 0
        max_win_streak = max(max_win_streak, win_streak)
        max_loss_streak = max(max_loss_streak, loss_streak)
    return {
        "max_drawdown_units": max_drawdown,
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
        "ending_profit_units": cumulative,
    }


def _funnel_summary(
    evaluation_funnel: Sequence[dict[str, Any]],
    verification_funnel: Sequence[dict[str, Any]],
    health: dict[str, Any],
) -> dict[str, Any]:
    summary = {
        "predictions": int(health.get("model_predictions") or 0),
        "evaluations": int(health.get("value_evaluations") or 0),
        "final_checks": int(health.get("final_quote_verifications") or 0),
        "registered": int(health.get("registered_picks") or 0),
        "closings": int(health.get("closing_finalizations") or 0),
        "settled": int(health.get("settled_picks") or 0),
        "clv_available": int(health.get("clv_available") or 0),
        "preliminary_candidates": 0,
        "preliminary_passes": 0,
        "final_candidates": 0,
        "final_passes": 0,
        "verifications_ready": 0,
        "verifications_rejected": 0,
        "evaluation_reasons": [],
        "verification_reasons": [],
    }
    reason_counts: dict[str, int] = defaultdict(int)
    for row in evaluation_funnel:
        stage = str(row.get("stage") or "")
        outcome = str(row.get("outcome") or "")
        count = int(row.get("count") or 0)
        if stage == "PRELIMINARY" and outcome == "CANDIDATE":
            summary["preliminary_candidates"] += count
        elif stage == "PRELIMINARY" and outcome == "PASS":
            summary["preliminary_passes"] += count
        elif stage == "FINAL" and outcome == "CANDIDATE":
            summary["final_candidates"] += count
        elif stage == "FINAL" and outcome == "PASS":
            summary["final_passes"] += count
        if outcome == "PASS":
            reason_counts[str(row.get("reason_code") or "UNKNOWN")] += count
    summary["evaluation_reasons"] = [
        {"reason": reason, "count": count}
        for reason, count in sorted(
            reason_counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]

    verification_reason_counts: dict[str, int] = defaultdict(int)
    for row in verification_funnel:
        status = str(row.get("status") or "")
        count = int(row.get("count") or 0)
        if status == "READY":
            summary["verifications_ready"] += count
        elif status == "REJECTED":
            summary["verifications_rejected"] += count
        for reason in row.get("reason_codes") or []:
            verification_reason_counts[str(reason)] += count
    summary["verification_reasons"] = [
        {"reason": reason, "count": count}
        for reason, count in sorted(
            verification_reason_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    return summary


def build_baseball_analytics_snapshot(
    rows: Sequence[dict[str, Any]],
    *,
    evaluation_funnel: Sequence[dict[str, Any]] = (),
    verification_funnel: Sequence[dict[str, Any]] = (),
    health: dict[str, Any] | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    now = as_of or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        now = now.replace(tzinfo=UTC)
    else:
        now = now.astimezone(UTC)
    materialized = tuple(dict(row) for row in rows)

    def since(days: int) -> tuple[dict[str, Any], ...]:
        cutoff = now - timedelta(days=days)
        return tuple(
            row
            for row in materialized
            if (stamp := _dt(row.get("registered_at"))) is not None
            and cutoff <= stamp <= now
        )

    weekly: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in materialized:
        stamp = _dt(row.get("registered_at"))
        if stamp is None:
            continue
        year, week, _ = stamp.isocalendar()
        weekly[f"{year}-W{week:02d}"].append(row)

    cohorts = {
        "selection": _cohort_rows(
            materialized,
            "selection",
            lambda r: str(r.get("selection") or "UNKNOWN").upper(),
        ),
        "bookmaker": _cohort_rows(
            materialized,
            "bookmaker",
            lambda r: str(r.get("bookmaker") or "UNKNOWN"),
        ),
        "league": _cohort_rows(
            materialized,
            "league",
            lambda r: str(r.get("league") or "UNKNOWN"),
        ),
        "model_version": _cohort_rows(
            materialized,
            "model_version",
            lambda r: str(r.get("model_version") or "UNKNOWN"),
        ),
        "favorite_status": _cohort_rows(
            materialized,
            "favorite_status",
            _favorite_status,
        ),
        "model_probability": _cohort_rows(
            materialized,
            "model_p_bucket",
            lambda r: _bucket_probability(r.get("model_probability")),
        ),
        "market_probability": _cohort_rows(
            materialized,
            "market_p_bucket",
            lambda r: _bucket_probability(r.get("market_probability")),
        ),
        "entry_odds": _cohort_rows(
            materialized,
            "odds_bucket",
            lambda r: _bucket_odds(r.get("entry_odds")),
        ),
        "edge": _cohort_rows(
            materialized,
            "edge_bucket",
            lambda r: _bucket_edge(r.get("edge")),
        ),
        "ev": _cohort_rows(
            materialized,
            "ev_bucket",
            lambda r: _bucket_ev(r.get("expected_value_per_unit")),
        ),
        "uncertainty": _cohort_rows(
            materialized,
            "uncertainty_bucket",
            lambda r: _bucket_uncertainty(r.get("uncertainty_metric")),
        ),
        "t_minus": _cohort_rows(
            materialized,
            "t_minus_bucket",
            _bucket_t_minus,
        ),
        "clv_sign": _cohort_rows(
            materialized,
            "clv_sign",
            _clv_sign,
        ),
    }

    return {
        "contract_version": ANALYTICS_CONTRACT_VERSION,
        "generated_at": now.isoformat(),
        "definitions": {
            "universe": "Every immutable registered Baseball paper Moneyline pick.",
            "windowing": (
                "7d/30d cohorts use registered_at, so a decision remains in the "
                "cohort it was actually made in."
            ),
            "roi": (
                "Sum of realized profit-per-unit divided by settled picks; pushes "
                "consume one unit of stake and return zero profit."
            ),
            "calibration_gap": (
                "Observed win rate minus mean model probability on graded WIN/LOSS picks."
            ),
            "clv": (
                "Selected-side closing market probability minus entry market probability "
                "when a valid closing quote exists."
            ),
            "gate_slippage": (
                "Final registered price/edge/EV minus the preliminary candidate values "
                "before final quote verification."
            ),
            "sample_bands": {
                "SIGNAL_ONLY": "<20 graded picks",
                "MONITOR": "20-49 graded picks",
                "PROVISIONAL_EVIDENCE": "50-99 graded picks",
                "STABILITY_REVIEW": "100+ graded picks",
            },
        },
        "windows": {
            "lifetime": _cohort_metrics(materialized),
            "last_30d": _cohort_metrics(since(30)),
            "last_7d": _cohort_metrics(since(7)),
        },
        "weekly": [
            {"week": week, **_cohort_metrics(weekly[week])}
            for week in sorted(weekly, reverse=True)
        ],
        "risk": _streak_and_drawdown(materialized),
        "funnel": _funnel_summary(
            evaluation_funnel,
            verification_funnel,
            health or {},
        ),
        "cohorts": cohorts,
    }


def _fmt(
    value: Any,
    suffix: str = "",
    *,
    signed: bool = False,
    digits: int = 2,
) -> str:
    if value is None:
        return "—"
    number = _num(value)
    if number is None:
        return escape(str(value))
    prefix = "+" if signed and number > 0 else ""
    return f"{prefix}{number:.{digits}f}{suffix}"


def _pnl(minor: Any) -> str:
    try:
        return f"{int(minor) / 100:+.0f} RSD"
    except (TypeError, ValueError):
        return "—"


def _metric_class(value: Any) -> str:
    number = _num(value)
    if number is None or abs(number) < 1e-12:
        return ""
    return "positive" if number > 0 else "negative"


def _metrics_table(
    title: str,
    rows: Sequence[dict[str, Any]],
    dimension: str,
) -> str:
    if not rows:
        body = '<tr><td class="empty" colspan="11">No cohort evidence yet.</td></tr>'
    else:
        body = "".join(
            f"""<tr>
<td><b>{escape(str(row.get(dimension) or "—"))}</b></td>
<td>{row.get("registered_n", 0)}</td>
<td>{row.get("settled_n", 0)}</td>
<td>{row.get("wins", 0)}-{row.get("losses", 0)}-{row.get("pushes", 0)}</td>
<td>{_fmt(row.get("win_rate_pct"), "%")}</td>
<td>{_fmt(row.get("expected_win_rate_pct"), "%")}</td>
<td class="{_metric_class(row.get("calibration_gap_pp"))}">{_fmt(row.get("calibration_gap_pp"), "pp", signed=True)}</td>
<td class="{_metric_class(row.get("roi_pct"))}">{_fmt(row.get("roi_pct"), "%", signed=True)}</td>
<td class="{_metric_class(row.get("avg_clv_probability_delta_pct"))}">{_fmt(row.get("avg_clv_probability_delta_pct"), "pp", signed=True)}</td>
<td>{_fmt(row.get("brier_score"), digits=4)}</td>
<td>{escape(str(row.get("sample_band") or "—"))}</td>
</tr>"""
            for row in rows
        )
    return f"""
<section class="panel table-panel">
<div class="panel-title"><b>{escape(title)}</b><span>registered → settled → calibration → price quality</span></div>
<div class="table-wrap"><table><thead><tr>
<th>{escape(dimension.replace("_", " ").title())}</th><th>Reg</th><th>Settled</th><th>W-L-P</th>
<th>Win%</th><th>Exp%</th><th>Cal gap</th><th>ROI</th><th>Avg CLV Δ</th><th>Brier</th><th>Evidence</th>
</tr></thead><tbody>{body}</tbody></table></div></section>"""


def render_baseball_analytics_html(snapshot: dict[str, Any]) -> str:
    lifetime = snapshot["windows"]["lifetime"]
    risk = snapshot["risk"]
    funnel = snapshot["funnel"]
    sample_band = str(lifetime.get("sample_band") or "SIGNAL_ONLY")
    sample_note = {
        "SIGNAL_ONLY": (
            "Too few graded picks for performance conclusions. Read this page as "
            "instrumentation, not proof of edge."
        ),
        "MONITOR": "Early signal only. Cohort direction can still reverse quickly.",
        "PROVISIONAL_EVIDENCE": (
            "Useful provisional evidence, but regime and calibration stability still "
            "need confirmation."
        ),
        "STABILITY_REVIEW": (
            "Sample is large enough for stability review; continue checking regime "
            "drift and CLV persistence."
        ),
    }.get(sample_band, "")

    cards = [
        ("Registered", lifetime.get("registered_n"), "immutable paper picks", ""),
        ("Settled", lifetime.get("settled_n"), "closed outcomes", ""),
        (
            "W / L / P",
            f"{lifetime.get('wins', 0)} / {lifetime.get('losses', 0)} / {lifetime.get('pushes', 0)}",
            "",
            "",
        ),
        (
            "ROI",
            _fmt(lifetime.get("roi_pct"), "%", signed=True),
            "flat 1u",
            _metric_class(lifetime.get("roi_pct")),
        ),
        (
            "Paper P/L",
            _pnl(lifetime.get("paper_pnl_minor")),
            "300 RSD singles",
            _metric_class(lifetime.get("paper_pnl_minor")),
        ),
        (
            "Avg edge",
            _fmt(lifetime.get("avg_edge_pct"), "%", signed=True),
            "model p - market p",
            _metric_class(lifetime.get("avg_edge_pct")),
        ),
        (
            "Avg EV",
            _fmt(lifetime.get("avg_ev_pct"), "%", signed=True),
            "at entry",
            _metric_class(lifetime.get("avg_ev_pct")),
        ),
        (
            "Cal gap",
            _fmt(lifetime.get("calibration_gap_pp"), "pp", signed=True),
            "observed - expected",
            _metric_class(lifetime.get("calibration_gap_pp")),
        ),
        ("Brier", _fmt(lifetime.get("brier_score"), digits=4), "probability error", ""),
        (
            "Log loss",
            _fmt(lifetime.get("log_loss"), digits=4),
            "probability penalty",
            "",
        ),
        (
            "Avg CLV Δ",
            _fmt(
                lifetime.get("avg_clv_probability_delta_pct"),
                "pp",
                signed=True,
            ),
            "close p - entry p",
            _metric_class(lifetime.get("avg_clv_probability_delta_pct")),
        ),
        (
            "+CLV",
            _fmt(lifetime.get("positive_clv_rate_pct"), "%"),
            f"{lifetime.get('clv_count', 0)} priced closes",
            "",
        ),
    ]
    cards_html = "".join(
        f'<article class="kpi"><small>{escape(str(label))}</small><b class="{css}">{escape(str(value))}</b><span>{escape(str(note))}</span></article>'
        for label, value, note, css in cards
    )

    funnel_items = [
        ("Predictions", funnel.get("predictions", 0)),
        ("Evaluations", funnel.get("evaluations", 0)),
        ("Prelim candidate", funnel.get("preliminary_candidates", 0)),
        ("Prelim pass", funnel.get("preliminary_passes", 0)),
        ("Final checks", funnel.get("final_checks", 0)),
        ("Verification ready", funnel.get("verifications_ready", 0)),
        ("Verification reject", funnel.get("verifications_rejected", 0)),
        ("Registered", funnel.get("registered", 0)),
        ("Closings", funnel.get("closings", 0)),
        ("Settled", funnel.get("settled", 0)),
        ("CLV available", funnel.get("clv_available", 0)),
    ]
    funnel_html = "".join(
        f'<div class="metric"><small>{escape(label)}</small><b>{value}</b></div>'
        for label, value in funnel_items
    )

    avg_t_minus = lifetime.get("avg_t_minus_minutes")
    gate_items = [
        (
            "Avg prelim→final odds Δ",
            _fmt(
                lifetime.get("avg_prelim_to_final_odds_delta"),
                signed=True,
                digits=3,
            ),
        ),
        (
            "Avg prelim→final edge Δ",
            _fmt(
                lifetime.get("avg_prelim_to_final_edge_delta_pp"),
                "pp",
                signed=True,
            ),
        ),
        (
            "Avg prelim→final EV Δ",
            _fmt(
                lifetime.get("avg_prelim_to_final_ev_delta_pp"),
                "pp",
                signed=True,
            ),
        ),
        (
            "Avg final quote age",
            _fmt(lifetime.get("avg_final_quote_age_seconds"), "s"),
        ),
        (
            "Avg T-minus",
            _fmt(avg_t_minus / 60 if avg_t_minus is not None else None, "h"),
        ),
        (
            "EV realization gap",
            _fmt(lifetime.get("ev_realization_gap_pp"), "pp", signed=True),
        ),
        (
            "Max drawdown",
            _fmt(risk.get("max_drawdown_units"), "u", signed=True),
        ),
        ("Max W streak", risk.get("max_win_streak", 0)),
        ("Max L streak", risk.get("max_loss_streak", 0)),
    ]
    gate_html = "".join(
        f"<div><small>{escape(label)}</small><b>{escape(str(value))}</b></div>"
        for label, value in gate_items
    )

    window_rows = []
    for key, label in (
        ("lifetime", "Lifetime"),
        ("last_30d", "Last 30d"),
        ("last_7d", "Last 7d"),
    ):
        row = snapshot["windows"][key]
        window_rows.append(
            f"""<tr><td><b>{label}</b></td><td>{row.get("registered_n", 0)}</td><td>{row.get("settled_n", 0)}</td>
<td>{row.get("wins", 0)}-{row.get("losses", 0)}-{row.get("pushes", 0)}</td>
<td>{_fmt(row.get("win_rate_pct"), "%")}</td><td>{_fmt(row.get("expected_win_rate_pct"), "%")}</td>
<td>{_fmt(row.get("calibration_gap_pp"), "pp", signed=True)}</td><td>{_fmt(row.get("roi_pct"), "%", signed=True)}</td>
<td>{_fmt(row.get("avg_clv_probability_delta_pct"), "pp", signed=True)}</td><td>{escape(str(row.get("sample_band") or "—"))}</td></tr>"""
        )

    weekly = snapshot.get("weekly") or []
    weekly_rows = (
        "".join(
            f"""<tr><td><b>{escape(str(row.get("week")))}</b></td><td>{row.get("registered_n", 0)}</td><td>{row.get("settled_n", 0)}</td>
<td>{row.get("wins", 0)}-{row.get("losses", 0)}-{row.get("pushes", 0)}</td>
<td>{_fmt(row.get("roi_pct"), "%", signed=True)}</td><td>{_fmt(row.get("avg_ev_pct"), "%", signed=True)}</td>
<td>{_fmt(row.get("calibration_gap_pp"), "pp", signed=True)}</td><td>{_fmt(row.get("avg_clv_probability_delta_pct"), "pp", signed=True)}</td></tr>"""
            for row in weekly[:26]
        )
        or '<tr><td class="empty" colspan="8">No weekly evidence yet.</td></tr>'
    )

    eval_reasons = funnel.get("evaluation_reasons") or []
    verify_reasons = funnel.get("verification_reasons") or []
    reason_html = "".join(
        f"<tr><td>{escape(str(row.get('reason')))}</td><td>{row.get('count', 0)}</td><td>Evaluation PASS</td></tr>"
        for row in eval_reasons
    ) + "".join(
        f"<tr><td>{escape(str(row.get('reason')))}</td><td>{row.get('count', 0)}</td><td>Verification REJECTED</td></tr>"
        for row in verify_reasons
    )
    if not reason_html:
        reason_html = (
            '<tr><td class="empty" colspan="3">'
            "No blocked-gate reason evidence yet.</td></tr>"
        )

    cohorts = snapshot.get("cohorts") or {}
    cohort_sections = "".join(
        (
            _metrics_table(
                "Side",
                cohorts.get("selection", []),
                "selection",
            ),
            _metrics_table(
                "Favorite / underdog",
                cohorts.get("favorite_status", []),
                "favorite_status",
            ),
            _metrics_table(
                "Bookmaker",
                cohorts.get("bookmaker", []),
                "bookmaker",
            ),
            _metrics_table(
                "League",
                cohorts.get("league", []),
                "league",
            ),
            _metrics_table(
                "Model version",
                cohorts.get("model_version", []),
                "model_version",
            ),
            _metrics_table(
                "Model probability calibration",
                cohorts.get("model_probability", []),
                "model_p_bucket",
            ),
            _metrics_table(
                "Market implied probability",
                cohorts.get("market_probability", []),
                "market_p_bucket",
            ),
            _metrics_table(
                "Entry odds",
                cohorts.get("entry_odds", []),
                "odds_bucket",
            ),
            _metrics_table(
                "Edge",
                cohorts.get("edge", []),
                "edge_bucket",
            ),
            _metrics_table(
                "Expected value",
                cohorts.get("ev", []),
                "ev_bucket",
            ),
            _metrics_table(
                "Uncertainty metric",
                cohorts.get("uncertainty", []),
                "uncertainty_bucket",
            ),
            _metrics_table(
                "Registration timing",
                cohorts.get("t_minus", []),
                "t_minus_bucket",
            ),
            _metrics_table(
                "CLV sign",
                cohorts.get("clv_sign", []),
                "clv_sign",
            ),
        )
    )

    return f"""
<section class="section-title"><div><small>ANALYTICS</small><h2>Baseball Moneyline lab</h2></div>
<span>probability quality · price quality · execution · realized returns</span></section>
<div class="kpi-grid">{cards_html}</div>
<section class="panel"><div class="panel-title"><b>Evidence status · {escape(sample_band)}</b><span>{lifetime.get("graded_n", 0)} graded picks</span></div>
<p class="muted">{escape(sample_note)} 95% Wilson win-rate interval: {_fmt(lifetime.get("win_rate_wilson_95_low_pct"), "%")} to {_fmt(lifetime.get("win_rate_wilson_95_high_pct"), "%")}.</p></section>
<section class="split"><article class="panel"><div class="panel-title"><b>Decision funnel</b><span>where candidates disappear</span></div><div class="metric-grid">{funnel_html}</div></article>
<article class="panel"><div class="panel-title"><b>Execution / risk diagnostics</b><span>final gate + variance</span></div><div class="budget-grid">{gate_html}</div></article></section>
<section class="panel table-panel"><div class="panel-title"><b>Blocked-gate reasons</b><span>PASS and final verification rejects</span></div>
<div class="table-wrap"><table><thead><tr><th>Reason</th><th>N</th><th>Stage</th></tr></thead><tbody>{reason_html}</tbody></table></div></section>
<section class="panel table-panel"><div class="panel-title"><b>Performance windows</b><span>decision-time cohorts</span></div>
<div class="table-wrap"><table><thead><tr><th>Window</th><th>Reg</th><th>Settled</th><th>W-L-P</th><th>Win%</th><th>Exp%</th><th>Cal gap</th><th>ROI</th><th>Avg CLV Δ</th><th>Evidence</th></tr></thead><tbody>{"".join(window_rows)}</tbody></table></div></section>
<section class="panel table-panel"><div class="panel-title"><b>Weekly regime tracker</b><span>latest 26 ISO weeks</span></div>
<div class="table-wrap"><table><thead><tr><th>Week</th><th>Reg</th><th>Settled</th><th>W-L-P</th><th>ROI</th><th>Avg EV</th><th>Cal gap</th><th>Avg CLV Δ</th></tr></thead><tbody>{weekly_rows}</tbody></table></div></section>
{cohort_sections}
<section class="research-note"><b>How to read this page</b>
<p>ROI answers whether paper bets made money. Calibration, Brier and log loss answer whether the model probabilities were honest. CLV answers whether we consistently bought a better price than the close. Gate slippage answers whether final verification preserved or destroyed the preliminary edge. Cohorts show where any signal actually lives instead of letting one aggregate number hide regime problems.</p>
<p>Contract: {escape(str(snapshot.get("contract_version")))} · Analytics are read-only and use immutable production paper-pick facts.</p></section>"""
