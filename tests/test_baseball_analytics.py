from datetime import UTC, datetime, timedelta

from quantbot.baseball.analytics import (
    build_baseball_analytics_snapshot,
    render_baseball_analytics_html,
)


def _row(
    *,
    pick_id: str,
    outcome: str | None,
    profit: float | None,
    model_probability: float = 0.58,
    market_probability: float = 0.53,
    clv_delta: float | None = None,
) -> dict:
    now = datetime(2026, 9, 29, 10, 0, tzinfo=UTC)
    return {
        "pick_id": pick_id,
        "selection": "home",
        "bookmaker": "Bet365",
        "league": "MLB",
        "model_version": "team-strength-poisson-baseline-v1",
        "entry_odds": 1.90,
        "model_probability": model_probability,
        "market_probability": market_probability,
        "edge": model_probability - market_probability,
        "expected_value_per_unit": 0.102,
        "uncertainty_metric": 0.04,
        "registered_at": now - timedelta(days=1),
        "kickoff_at": now - timedelta(hours=20),
        "settlement_outcome": outcome,
        "profit_per_unit": profit,
        "paper_profit_minor": (None if profit is None else round(profit * 30_000)),
        "clv_status": "AVAILABLE" if clv_delta is not None else None,
        "clv_probability_delta": clv_delta,
        "clv_price_ratio": 1.03 if clv_delta is not None else None,
        "preliminary_odds": 1.92,
        "preliminary_edge": 0.052,
        "preliminary_ev": 0.11,
        "final_quote_age_seconds": 30,
    }


def test_analytics_separates_probability_price_and_realized_performance() -> None:
    rows = [
        _row(pick_id="1", outcome="WIN", profit=0.90, clv_delta=0.02),
        _row(pick_id="2", outcome="LOSS", profit=-1.0, clv_delta=-0.01),
        _row(pick_id="3", outcome=None, profit=None),
    ]
    snapshot = build_baseball_analytics_snapshot(
        rows,
        evaluation_funnel=[
            {
                "stage": "PRELIMINARY",
                "outcome": "CANDIDATE",
                "reason_code": "NONE",
                "count": 3,
            },
            {
                "stage": "PRELIMINARY",
                "outcome": "PASS",
                "reason_code": "EDGE_BELOW_THRESHOLD",
                "count": 4,
            },
        ],
        verification_funnel=[
            {"status": "READY", "reason_codes": [], "count": 3},
            {
                "status": "REJECTED",
                "reason_codes": ["PRICE_DETERIORATED"],
                "count": 1,
            },
        ],
        health={
            "model_predictions": 10,
            "value_evaluations": 7,
            "final_quote_verifications": 4,
            "registered_picks": 3,
            "closing_finalizations": 2,
            "settled_picks": 2,
            "clv_available": 2,
        },
        as_of=datetime(2026, 9, 29, 12, 0, tzinfo=UTC),
    )

    lifetime = snapshot["windows"]["lifetime"]
    assert lifetime["registered_n"] == 3
    assert lifetime["settled_n"] == 2
    assert lifetime["wins"] == 1
    assert lifetime["losses"] == 1
    assert round(lifetime["roi_pct"], 2) == -5.00
    assert lifetime["brier_score"] is not None
    assert lifetime["log_loss"] is not None
    assert round(lifetime["avg_clv_probability_delta_pct"], 2) == 0.50
    assert lifetime["sample_band"] == "SIGNAL_ONLY"
    assert snapshot["funnel"]["preliminary_passes"] == 4
    assert snapshot["funnel"]["verifications_rejected"] == 1
    assert snapshot["funnel"]["evaluation_reasons"][0]["reason"] == (
        "EDGE_BELOW_THRESHOLD"
    )


def test_analytics_html_exposes_baseball_specific_diagnostics() -> None:
    snapshot = build_baseball_analytics_snapshot(
        [_row(pick_id="1", outcome="WIN", profit=0.90, clv_delta=0.02)],
        health={"registered_picks": 1, "settled_picks": 1, "clv_available": 1},
        as_of=datetime(2026, 9, 29, 12, 0, tzinfo=UTC),
    )

    html = render_baseball_analytics_html(snapshot)

    assert "Baseball Moneyline lab" in html
    assert "Decision funnel" in html
    assert "Execution / risk diagnostics" in html
    assert "Model probability calibration" in html
    assert "Market implied probability" in html
    assert "Favorite / underdog" in html
    assert "Registration timing" in html
    assert "SIGNAL_ONLY" in html
