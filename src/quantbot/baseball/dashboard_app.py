"""Read-only production observability dashboard for QuantBet Baseball."""

from __future__ import annotations

import html
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import psycopg
from psycopg.rows import dict_row

from .db import database_url_from_env

PLAYABLE_BOOKS = ("bet365", "1xbet")
TARGET_PAPER_STAKE_RSD = 300


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return str(value)


def _age_seconds(value: Any, *, now: datetime) -> float | None:
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
        return None
    return max(0.0, (now - stamp.astimezone(UTC)).total_seconds())


def _query_one(connection: psycopg.Connection, sql: str, params=()) -> dict[str, Any]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone() or {}


def _query_all(connection: psycopg.Connection, sql: str, params=()) -> list[dict[str, Any]]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def _relation_exists(connection: psycopg.Connection, name: str) -> bool:
    row = _query_one(connection, "SELECT to_regclass(%s) IS NOT NULL AS present", (name,))
    return bool(row.get("present"))


def _column_exists(
    connection: psycopg.Connection,
    *,
    table: str,
    column: str,
) -> bool:
    row = _query_one(
        connection,
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = %s
        ) AS present
        """,
        (table, column),
    )
    return bool(row.get("present"))


def _safe_one(
    connection: psycopg.Connection,
    sql: str,
    params=(),
) -> dict[str, Any]:
    try:
        return _query_one(connection, sql, params)
    except psycopg.Error:
        return {}


def _safe_all(
    connection: psycopg.Connection,
    sql: str,
    params=(),
) -> list[dict[str, Any]]:
    try:
        return _query_all(connection, sql, params)
    except psycopg.Error:
        return []


def _system_snapshot(connection: psycopg.Connection, *, now: datetime) -> dict[str, Any]:
    latest_runtime = _safe_one(
        connection,
        """
        SELECT run_id, started_at, finished_at, collection_enabled, mode, status, stats
        FROM runtime_cycles
        ORDER BY finished_at DESC, run_id DESC
        LIMIT 1
        """,
    )
    latest_gate = _safe_one(
        connection,
        """
        SELECT target, assessed_at, verdict, reason_codes,
               daily_request_budget, cycle_request_cap,
               cron_interval_minutes, cycles_per_day,
               worst_case_daily_requests, request_headroom,
               daily_reserve_required, paper_mode,
               collection_enabled, api_key_configured,
               raw_archive_configured, migrations_current,
               runtime_fresh, canary_passed, latest_canary_id
        FROM activation_gate_assessments
        ORDER BY assessed_at DESC, assessment_id DESC
        LIMIT 1
        """,
    )
    latest_canary = _safe_one(
        connection,
        """
        SELECT canary_id, started_at, finished_at, status,
               max_api_requests, api_requests,
               fixture_observations_inserted, observations_inserted,
               errors, archive_verified, db_write_verified, reason_codes
        FROM operational_canary_runs
        ORDER BY finished_at DESC, canary_id DESC
        LIMIT 1
        """,
    )
    latest_collection = _safe_one(
        connection,
        """
        SELECT cycle_id, started_at, finished_at, status, execution_mode,
               games_seen, pregame_games, games_selected, odds_calls,
               raw_market_rows, canonical_rows, observations_inserted,
               api_requests, api_remaining, errors
        FROM collection_cycles
        ORDER BY finished_at DESC, cycle_id DESC
        LIMIT 1
        """,
    )
    evidence = _safe_one(
        connection,
        """
        SELECT
          (SELECT COUNT(*) FROM fixtures) AS fixtures,
          (SELECT COUNT(*) FROM fixture_observations) AS fixture_observations,
          (SELECT COUNT(*) FROM odds_observations) AS odds_observations,
          (SELECT COUNT(DISTINCT bookmaker) FROM odds_observations) AS bookmakers,
          (SELECT COUNT(*) FROM model_predictions) AS model_predictions,
          (SELECT COUNT(*) FROM value_evaluations) AS value_evaluations,
          (SELECT COUNT(*) FROM final_quote_verifications) AS final_quote_verifications,
          (SELECT COUNT(*) FROM registered_picks) AS registered_picks,
          (SELECT COUNT(*) FROM pick_settlements) AS settled_picks,
          (SELECT COUNT(*) FROM game_result_facts) AS result_facts,
          (SELECT COUNT(*) FROM pick_settlements WHERE clv_status = 'AVAILABLE') AS clv_available,
          (SELECT MAX(observed_at) FROM fixture_observations) AS latest_fixture_observed_at,
          (SELECT MAX(observed_at) FROM odds_observations) AS latest_odds_observed_at
        """,
    )

    runtime_age = _age_seconds(latest_runtime.get("finished_at"), now=now)
    odds_age = _age_seconds(evidence.get("latest_odds_observed_at"), now=now)
    fixture_age = _age_seconds(evidence.get("latest_fixture_observed_at"), now=now)

    budget = {
        "daily_request_budget": latest_gate.get("daily_request_budget"),
        "cycle_request_cap": latest_gate.get("cycle_request_cap"),
        "cron_interval_minutes": latest_gate.get("cron_interval_minutes"),
        "worst_case_daily_requests": latest_gate.get("worst_case_daily_requests"),
        "request_headroom": latest_gate.get("request_headroom"),
        "daily_reserve_required": latest_gate.get("daily_reserve_required"),
    }
    budget_safe = None
    if (
        budget["request_headroom"] is not None
        and budget["daily_reserve_required"] is not None
    ):
        budget_safe = int(budget["request_headroom"]) >= int(
            budget["daily_reserve_required"]
        )

    return {
        "latest_runtime": latest_runtime,
        "latest_gate": latest_gate,
        "latest_canary": latest_canary,
        "latest_collection": latest_collection,
        "evidence": evidence,
        "runtime_age_seconds": runtime_age,
        "odds_age_seconds": odds_age,
        "fixture_age_seconds": fixture_age,
        "budget": budget,
        "budget_safe": budget_safe,
    }


def _coverage_snapshot(connection: psycopg.Connection) -> dict[str, Any]:
    bookmakers = _safe_all(
        connection,
        """
        SELECT lower(bookmaker) AS bookmaker,
               COUNT(*)::BIGINT AS observations,
               COUNT(DISTINCT game_id)::BIGINT AS games,
               MAX(observed_at) AS latest_observed_at
        FROM odds_observations
        GROUP BY lower(bookmaker)
        ORDER BY observations DESC, bookmaker
        """,
    )
    leagues = _safe_all(
        connection,
        """
        WITH latest AS (
            SELECT DISTINCT ON (game_id)
                   game_id, league, kickoff_at, provider_status, observed_at
            FROM fixture_observations
            ORDER BY game_id, observed_at DESC, fixture_observation_id DESC
        )
        SELECT league,
               COUNT(*)::BIGINT AS games,
               COUNT(*) FILTER (WHERE kickoff_at > CURRENT_TIMESTAMP)::BIGINT AS upcoming,
               MAX(observed_at) AS latest_observed_at
        FROM latest
        GROUP BY league
        ORDER BY games DESC, league
        """,
    )
    playable = [row for row in bookmakers if row.get("bookmaker") in PLAYABLE_BOOKS]
    intelligence = [
        row for row in bookmakers if row.get("bookmaker") not in PLAYABLE_BOOKS
    ]
    return {
        "bookmakers": bookmakers,
        "playable": playable,
        "intelligence_only": intelligence,
        "leagues": leagues,
    }


def _performance_snapshot(connection: psycopg.Connection) -> dict[str, Any]:
    performance = (
        _safe_one(connection, "SELECT * FROM baseball_moneyline_performance")
        if _relation_exists(connection, "baseball_moneyline_performance")
        else {}
    )
    breakdown = (
        _safe_all(
            connection,
            """
            SELECT dimension, dimension_value, settled_picks,
                   realized_profit_per_unit, roi_per_unit_staked,
                   brier_score, log_loss, average_clv_probability_delta
            FROM baseball_moneyline_performance_breakdown
            ORDER BY dimension, settled_picks DESC, dimension_value
            """,
        )
        if _relation_exists(connection, "baseball_moneyline_performance_breakdown")
        else []
    )
    dashboard = (
        _safe_one(connection, "SELECT * FROM baseball_moneyline_dashboard")
        if _relation_exists(connection, "baseball_moneyline_dashboard")
        else {}
    )
    stake_enforced = _column_exists(
        connection,
        table="registered_picks",
        column="paper_stake_minor",
    )
    return {
        "performance": performance,
        "dashboard": dashboard,
        "breakdown": breakdown,
        "stake_enforced": stake_enforced,
        "target_stake_rsd": TARGET_PAPER_STAKE_RSD,
    }


def _research_rows(connection: psycopg.Connection, *, limit: int = 100) -> dict[str, Any]:
    picks = _safe_all(
        connection,
        """
        WITH latest_fixture AS (
            SELECT DISTINCT ON (game_id)
                   game_id, league, home_team_name, away_team_name, kickoff_at
            FROM fixture_observations
            ORDER BY game_id, observed_at DESC, fixture_observation_id DESC
        )
        SELECT r.pick_id, r.game_id, f.league, f.home_team_name, f.away_team_name,
               r.kickoff_at, r.registered_at, r.market_family, r.selection,
               lower(r.bookmaker) AS bookmaker, r.entry_odds,
               r.model_probability, r.market_probability, r.fair_decimal_odds,
               r.edge, r.expected_value_per_unit, r.uncertainty_metric,
               r.model_version, r.feature_snapshot_ref,
               s.outcome AS settlement_outcome, s.profit_per_unit,
               s.clv_status, s.closing_odds, s.clv_probability_delta,
               s.settled_at
        FROM registered_picks r
        LEFT JOIN latest_fixture f ON f.game_id = r.game_id
        LEFT JOIN pick_settlements s ON s.pick_id = r.pick_id
        ORDER BY r.registered_at DESC, r.pick_id DESC
        LIMIT %s
        """,
        (limit,),
    )
    decisions = _safe_all(
        connection,
        """
        SELECT evaluation_id, game_id, lower(bookmaker) AS bookmaker,
               selection, stage, evaluated_at, selected_odds,
               market_probability, model_probability, fair_decimal_odds,
               edge, expected_value_per_unit, uncertainty_metric,
               outcome, reason_code
        FROM value_evaluations
        ORDER BY evaluated_at DESC, evaluation_id DESC
        LIMIT %s
        """,
        (limit,),
    )
    return {"picks": picks, "decisions": decisions}


def build_dashboard_snapshot(database_url: str | None = None) -> dict[str, Any]:
    """Read a complete dashboard snapshot without mutating production state."""

    now = _utcnow()
    url = database_url or database_url_from_env()
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute("SET default_transaction_read_only = on")
        connection.execute("SET statement_timeout = '4000ms'")
        system = _system_snapshot(connection, now=now)
        coverage = _coverage_snapshot(connection)
        performance = _performance_snapshot(connection)
        research = _research_rows(connection)

    return {
        "generated_at": now.isoformat(),
        "read_only": True,
        "playable_books": list(PLAYABLE_BOOKS),
        "system": system,
        "coverage": coverage,
        "performance": performance,
        "research": research,
    }


def _fmt_int(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return html.escape(str(value))


def _fmt_num(value: Any, digits: int = 2) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return html.escape(str(value))


def _fmt_pct(value: Any, digits: int = 1) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return html.escape(str(value))


def _fmt_age(seconds: Any) -> str:
    if seconds is None:
        return "no evidence"
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return "unknown"
    if value < 60:
        return f"{value:.0f}s ago"
    if value < 3600:
        return f"{value / 60:.0f}m ago"
    if value < 86400:
        return f"{value / 3600:.1f}h ago"
    return f"{value / 86400:.1f}d ago"


def _lamp(label: str, state: str, detail: str) -> str:
    safe_state = state if state in {"green", "amber", "red", "muted"} else "muted"
    return (
        f'<div class="lamp-card"><span class="lamp {safe_state}"></span>'
        f'<div><strong>{html.escape(label)}</strong>'
        f'<small>{html.escape(detail)}</small></div></div>'
    )


def _metric(label: str, value: str, detail: str = "") -> str:
    detail_html = f"<small>{html.escape(detail)}</small>" if detail else ""
    return (
        '<div class="metric-card">'
        f"<span>{html.escape(label)}</span><strong>{value}</strong>{detail_html}</div>"
    )


def _health_lamps(snapshot: dict[str, Any]) -> str:
    system = snapshot["system"]
    gate = system["latest_gate"]
    runtime_age = system["runtime_age_seconds"]
    worker_state = (
        "green"
        if runtime_age is not None and runtime_age <= 30 * 60
        else "red"
    )
    odds_age = system["odds_age_seconds"]
    odds_state = "green" if odds_age is not None and odds_age <= 6 * 3600 else "amber"
    if system["evidence"].get("odds_observations", 0) == 0:
        odds_state = "red"

    collection_on = bool(gate.get("collection_enabled"))
    canary_passed = bool(gate.get("canary_passed"))
    gate_state = "green" if canary_passed else "amber"
    collection_detail = "enabled" if collection_on else "intentionally paused by gate"

    lamps = [
        _lamp("Database", "green", "read-only query OK"),
        _lamp("Worker heartbeat", worker_state, _fmt_age(runtime_age)),
        _lamp(
            "API credential",
            "green" if gate.get("api_key_configured") else "red",
            "configured" if gate.get("api_key_configured") else "missing",
        ),
        _lamp(
            "Raw archive",
            "green" if gate.get("raw_archive_configured") else "red",
            "configured" if gate.get("raw_archive_configured") else "missing",
        ),
        _lamp(
            "Migrations",
            "green" if gate.get("migrations_current") else "red",
            "current" if gate.get("migrations_current") else "behind",
        ),
        _lamp(
            "Paper safety",
            "green" if gate.get("paper_mode") else "red",
            "PAPER mode" if gate.get("paper_mode") else "unsafe",
        ),
        _lamp("Collection", "green" if collection_on else "amber", collection_detail),
        _lamp(
            "Acceptance",
            gate_state,
            "canary passed" if canary_passed else "canary not yet passed",
        ),
        _lamp("Canonical odds", odds_state, _fmt_age(odds_age)),
        _lamp(
            "API budget",
            "green" if system.get("budget_safe") else "red",
            (
                f"headroom {system['budget'].get('request_headroom', '—')} / "
                f"reserve {system['budget'].get('daily_reserve_required', '—')}"
            ),
        ),
    ]
    return "".join(lamps)


def _overview(snapshot: dict[str, Any]) -> str:
    system = snapshot["system"]
    evidence = system["evidence"]
    perf = snapshot["performance"]["performance"]
    dboard = snapshot["performance"]["dashboard"]
    metrics = [
        _metric("Fixtures", _fmt_int(evidence.get("fixtures"))),
        _metric("Odds observations", _fmt_int(evidence.get("odds_observations"))),
        _metric("Model predictions", _fmt_int(evidence.get("model_predictions"))),
        _metric("Registered picks", _fmt_int(evidence.get("registered_picks"))),
        _metric("Settled", _fmt_int(evidence.get("settled_picks"))),
        _metric("CLV available", _fmt_int(evidence.get("clv_available"))),
        _metric("ROI / unit", _fmt_pct(perf.get("roi_per_unit_staked"))),
        _metric("Avg CLV Δ", _fmt_pct(perf.get("average_clv_probability_delta"))),
    ]
    canary = system["latest_canary"]
    collection = system["latest_collection"]
    lower = f"""
    <div class="two-col">
      <section class="panel">
        <div class="panel-head"><h2>Latest collection evidence</h2><span class="tag">DB FACT</span></div>
        <dl class="facts">
          <dt>Execution mode</dt><dd>{html.escape(str(collection.get("execution_mode") or "—"))}</dd>
          <dt>Status</dt><dd>{html.escape(str(collection.get("status") or "—"))}</dd>
          <dt>Games seen</dt><dd>{_fmt_int(collection.get("games_seen"))}</dd>
          <dt>Odds calls</dt><dd>{_fmt_int(collection.get("odds_calls"))}</dd>
          <dt>Raw market rows</dt><dd>{_fmt_int(collection.get("raw_market_rows"))}</dd>
          <dt>Canonical rows</dt><dd>{_fmt_int(collection.get("canonical_rows"))}</dd>
          <dt>Inserted odds</dt><dd>{_fmt_int(collection.get("observations_inserted"))}</dd>
          <dt>Errors</dt><dd>{_fmt_int(collection.get("errors"))}</dd>
        </dl>
      </section>
      <section class="panel">
        <div class="panel-head"><h2>Acceptance canary</h2><span class="tag">LAST RUN</span></div>
        <dl class="facts">
          <dt>Status</dt><dd>{html.escape(str(canary.get("status") or "—"))}</dd>
          <dt>Provider requests</dt><dd>{_fmt_int(canary.get("api_requests"))} / {_fmt_int(canary.get("max_api_requests"))}</dd>
          <dt>Fixture writes</dt><dd>{_fmt_int(canary.get("fixture_observations_inserted"))}</dd>
          <dt>Odds writes</dt><dd>{_fmt_int(canary.get("observations_inserted"))}</dd>
          <dt>Archive verified</dt><dd>{html.escape(str(canary.get("archive_verified") if canary else "—"))}</dd>
          <dt>DB write verified</dt><dd>{html.escape(str(canary.get("db_write_verified") if canary else "—"))}</dd>
          <dt>Reasons</dt><dd>{html.escape(", ".join(canary.get("reason_codes") or []) or "—")}</dd>
        </dl>
      </section>
    </div>
    <section class="panel">
      <div class="panel-head"><h2>Paper performance</h2><span class="tag">{TARGET_PAPER_STAKE_RSD} RSD TARGET STAKE</span></div>
      <div class="metrics compact">
        {_metric("Wins", _fmt_int(perf.get("wins")))}
        {_metric("Losses", _fmt_int(perf.get("losses")))}
        {_metric("Pushes", _fmt_int(perf.get("pushes")))}
        {_metric("P/L units", _fmt_num(perf.get("realized_profit_per_unit")))}
        {_metric("Pending settlement", _fmt_int(dboard.get("pending_settlement")))}
        {_metric("Positive CLV", _fmt_pct(perf.get("positive_clv_rate")))}
      </div>
    </section>
    """
    return (
        '<section class="hero"><div><span class="eyebrow">CONTROL PLANE</span>'
        "<h1>Baseball system observability</h1>"
        "<p>Worker, evidence, executable-market coverage and paper research from durable PostgreSQL facts.</p>"
        "</div><div class="hero-mark">⚾</div></section>"
        f'<div class="lamps">{_health_lamps(snapshot)}</div>'
        f'<div class="metrics">{"".join(metrics)}</div>{lower}'
    )


def _coverage(snapshot: dict[str, Any]) -> str:
    coverage = snapshot["coverage"]
    playable_rows = "".join(
        f"<tr><td>{html.escape(str(row.get('bookmaker')))}</td>"
        f"<td>{_fmt_int(row.get('games'))}</td>"
        f"<td>{_fmt_int(row.get('observations'))}</td>"
        f"<td>{html.escape(_fmt_age(_age_seconds(row.get('latest_observed_at'), now=_utcnow())))}</td></tr>"
        for row in coverage["playable"]
    ) or '<tr><td colspan="4" class="empty">No playable quote evidence yet</td></tr>'
    intelligence_rows = "".join(
        f"<tr><td>{html.escape(str(row.get('bookmaker')))}</td>"
        f"<td>{_fmt_int(row.get('games'))}</td>"
        f"<td>{_fmt_int(row.get('observations'))}</td></tr>"
        for row in coverage["intelligence_only"][:20]
    ) or '<tr><td colspan="3" class="empty">No intelligence-only quote evidence yet</td></tr>'
    league_rows = "".join(
        f"<tr><td>{html.escape(str(row.get('league')))}</td>"
        f"<td>{_fmt_int(row.get('games'))}</td>"
        f"<td>{_fmt_int(row.get('upcoming'))}</td>"
        f"<td>{html.escape(_iso(row.get('latest_observed_at')) or '—')}</td></tr>"
        for row in coverage["leagues"]
    )
    return f"""
    <section class="page-title"><span class="eyebrow">MARKET DATA</span><h1>Coverage</h1>
      <p>Playable execution is separated from market intelligence. Only Bet365 and 1xBet can become paper picks.</p>
    </section>
    <div class="two-col">
      <section class="panel">
        <div class="panel-head"><h2>Playable books</h2><span class="tag good">EXECUTABLE</span></div>
        <table><thead><tr><th>Book</th><th>Games</th><th>Obs</th><th>Freshness</th></tr></thead>
        <tbody>{playable_rows}</tbody></table>
      </section>
      <section class="panel">
        <div class="panel-head"><h2>Other books</h2><span class="tag">INTELLIGENCE ONLY</span></div>
        <table><thead><tr><th>Book</th><th>Games</th><th>Obs</th></tr></thead>
        <tbody>{intelligence_rows}</tbody></table>
      </section>
    </div>
    <section class="panel">
      <div class="panel-head"><h2>League fixture coverage</h2><span class="tag">LATEST PER GAME</span></div>
      <table><thead><tr><th>League</th><th>Games</th><th>Upcoming</th><th>Latest evidence</th></tr></thead>
      <tbody>{league_rows}</tbody></table>
    </section>
    """


def _research(snapshot: dict[str, Any]) -> str:
    picks = snapshot["research"]["picks"]
    decisions = snapshot["research"]["decisions"]
    pick_rows = "".join(
        f"<tr><td>{html.escape(str(row.get('away_team_name') or 'Away'))} @ {html.escape(str(row.get('home_team_name') or 'Home'))}</td>"
        f"<td>{html.escape(str(row.get('league') or '—'))}</td>"
        f"<td>{html.escape(str(row.get('selection') or '—').upper())}</td>"
        f"<td>{html.escape(str(row.get('bookmaker') or '—'))}</td>"
        f"<td>{_fmt_num(row.get('entry_odds'))}</td>"
        f"<td>{_fmt_pct(row.get('model_probability'))}</td>"
        f"<td>{_fmt_pct(row.get('edge'))}</td>"
        f"<td>{_fmt_pct(row.get('expected_value_per_unit'))}</td>"
        f"<td>{html.escape(str(row.get('settlement_outcome') or 'OPEN'))}</td>"
        f"<td>{_fmt_num(row.get('profit_per_unit'))}</td>"
        f"<td>{_fmt_pct(row.get('clv_probability_delta'))}</td></tr>"
        for row in picks
    ) or '<tr><td colspan="11" class="empty">No registered paper picks yet</td></tr>'
    decision_rows = "".join(
        f"<tr><td>{html.escape(str(row.get('game_id')))}</td>"
        f"<td>{html.escape(str(row.get('stage')))}</td>"
        f"<td>{html.escape(str(row.get('bookmaker')))}</td>"
        f"<td>{html.escape(str(row.get('selection')).upper())}</td>"
        f"<td>{html.escape(str(row.get('outcome')))}</td>"
        f"<td>{html.escape(str(row.get('reason_code')))}</td>"
        f"<td>{_fmt_pct(row.get('edge'))}</td>"
        f"<td>{_fmt_pct(row.get('expected_value_per_unit'))}</td></tr>"
        for row in decisions
    ) or '<tr><td colspan="8" class="empty">No model decisions yet</td></tr>'
    return f"""
    <section class="page-title"><span class="eyebrow">PAPER RESEARCH</span><h1>Research history</h1>
      <p>Immutable decision evidence. PASS is a valid output; registered picks require an executable Bet365 or 1xBet quote.</p>
    </section>
    <section class="panel wide">
      <div class="panel-head"><h2>Registered singles</h2><span class="tag">{TARGET_PAPER_STAKE_RSD} RSD</span></div>
      <div class="table-wrap"><table><thead><tr>
        <th>Game</th><th>League</th><th>Pick</th><th>Book</th><th>Odds</th>
        <th>Model P</th><th>Edge</th><th>EV</th><th>Result</th><th>P/L u</th><th>CLV Δ</th>
      </tr></thead><tbody>{pick_rows}</tbody></table></div>
    </section>
    <section class="panel wide">
      <div class="panel-head"><h2>Decision trail</h2><span class="tag">PICK + PASS</span></div>
      <div class="table-wrap"><table><thead><tr>
        <th>Game</th><th>Stage</th><th>Book</th><th>Side</th><th>Outcome</th>
        <th>Reason</th><th>Edge</th><th>EV</th>
      </tr></thead><tbody>{decision_rows}</tbody></table></div>
    </section>
    """


def _performance(snapshot: dict[str, Any]) -> str:
    perf = snapshot["performance"]["performance"]
    breakdown = snapshot["performance"]["breakdown"]
    stake_enforced = snapshot["performance"]["stake_enforced"]
    rows = "".join(
        f"<tr><td>{html.escape(str(row.get('dimension')))}</td>"
        f"<td>{html.escape(str(row.get('dimension_value')))}</td>"
        f"<td>{_fmt_int(row.get('settled_picks'))}</td>"
        f"<td>{_fmt_num(row.get('realized_profit_per_unit'))}</td>"
        f"<td>{_fmt_pct(row.get('roi_per_unit_staked'))}</td>"
        f"<td>{_fmt_num(row.get('brier_score'), 4)}</td>"
        f"<td>{_fmt_num(row.get('log_loss'), 4)}</td>"
        f"<td>{_fmt_pct(row.get('average_clv_probability_delta'))}</td></tr>"
        for row in breakdown
    ) or '<tr><td colspan="8" class="empty">No settled sample yet</td></tr>'
    stake_tag = (
        '<span class="tag good">300 RSD ENFORCED</span>'
        if stake_enforced
        else '<span class="tag warn">300 RSD MIGRATION PENDING</span>'
    )
    return f"""
    <section class="page-title"><span class="eyebrow">MODEL EVALUATION</span><h1>Performance</h1>
      <p>Paper profitability, calibration and closing-line quality. Small samples stay visible instead of being over-interpreted.</p>
    </section>
    <div class="metrics">
      {_metric("Settled picks", _fmt_int(perf.get("settled_picks")))}
      {_metric("ROI", _fmt_pct(perf.get("roi_per_unit_staked")))}
      {_metric("P/L units", _fmt_num(perf.get("realized_profit_per_unit")))}
      {_metric("Brier", _fmt_num(perf.get("brier_score"), 4))}
      {_metric("Log loss", _fmt_num(perf.get("log_loss"), 4))}
      {_metric("CLV coverage", _fmt_pct(perf.get("clv_coverage")))}
      {_metric("Avg CLV Δ", _fmt_pct(perf.get("average_clv_probability_delta")))}
      {_metric("Positive CLV", _fmt_pct(perf.get("positive_clv_rate")))}
    </div>
    <section class="panel">
      <div class="panel-head"><h2>Stake contract</h2>{stake_tag}</div>
      <p class="muted">Target single stake: {TARGET_PAPER_STAKE_RSD} RSD. The dashboard only labels it enforced when the production schema contains the immutable stake column.</p>
    </section>
    <section class="panel wide">
      <div class="panel-head"><h2>Breakdown</h2><span class="tag">OUT-OF-SAMPLE FACTS</span></div>
      <div class="table-wrap"><table><thead><tr>
        <th>Dimension</th><th>Value</th><th>N</th><th>P/L u</th><th>ROI</th><th>Brier</th><th>Log loss</th><th>CLV Δ</th>
      </tr></thead><tbody>{rows}</tbody></table></div>
    </section>
    """


def _health(snapshot: dict[str, Any]) -> str:
    system = snapshot["system"]
    gate = system["latest_gate"]
    runtime = system["latest_runtime"]
    budget = system["budget"]
    return f"""
    <section class="page-title"><span class="eyebrow">OPERATIONS</span><h1>System health</h1>
      <p>No synthetic green lights: every state below is derived from persisted production evidence.</p>
    </section>
    <div class="lamps">{_health_lamps(snapshot)}</div>
    <div class="two-col">
      <section class="panel"><div class="panel-head"><h2>Activation gate</h2><span class="tag">{html.escape(str(gate.get("verdict") or "NO DATA"))}</span></div>
        <dl class="facts">
          <dt>Target</dt><dd>{html.escape(str(gate.get("target") or "—"))}</dd>
          <dt>Assessed</dt><dd>{html.escape(_iso(gate.get("assessed_at")) or "—")}</dd>
          <dt>Reasons</dt><dd>{html.escape(", ".join(gate.get("reason_codes") or []) or "—")}</dd>
          <dt>Canary passed</dt><dd>{html.escape(str(gate.get("canary_passed") if gate else "—"))}</dd>
          <dt>Collection enabled</dt><dd>{html.escape(str(gate.get("collection_enabled") if gate else "—"))}</dd>
        </dl>
      </section>
      <section class="panel"><div class="panel-head"><h2>Runtime</h2><span class="tag">CRON */15</span></div>
        <dl class="facts">
          <dt>Status</dt><dd>{html.escape(str(runtime.get("status") or "—"))}</dd>
          <dt>Mode</dt><dd>{html.escape(str(runtime.get("mode") or "—"))}</dd>
          <dt>Finished</dt><dd>{html.escape(_iso(runtime.get("finished_at")) or "—")}</dd>
          <dt>Age</dt><dd>{html.escape(_fmt_age(system.get("runtime_age_seconds")))}</dd>
        </dl>
      </section>
    </div>
    <section class="panel"><div class="panel-head"><h2>API budget guard</h2><span class="tag good">BOUNDED</span></div>
      <div class="metrics compact">
        {_metric("Daily ceiling", _fmt_int(budget.get("daily_request_budget")))}
        {_metric("Cycle cap", _fmt_int(budget.get("cycle_request_cap")))}
        {_metric("Worst case/day", _fmt_int(budget.get("worst_case_daily_requests")))}
        {_metric("Headroom", _fmt_int(budget.get("request_headroom")))}
        {_metric("Required reserve", _fmt_int(budget.get("daily_reserve_required")))}
      </div>
    </section>
    """


def _features(snapshot: dict[str, Any]) -> str:
    odds = snapshot["system"]["evidence"].get("odds_observations", 0)
    cards = [
        ("Schedule / fixture spine", "ACTIVE", "API-Sports /games", "green"),
        ("Standings", "VERIFIED", "MLB + NPB live schema", "green"),
        ("Team statistics", "ARCHIVE AUDIT", "object schema inventory in progress", "amber"),
        ("Playable odds", "GATED", "Bet365 + 1xBet only", "green" if odds else "amber"),
        ("Starting pitchers", "EXTERNAL NEEDED", "verified structured source required", "amber"),
        ("Lineups / injuries", "EXTERNAL NEEDED", "verified point-in-time source required", "amber"),
        ("Park / roof", "FOUNDATION", "venue registry pending", "amber"),
        ("Weather", "FOUNDATION READY", "Open-Meteo contract implemented", "green"),
        ("Player props", "REJECTED", "outside product scope", "muted"),
    ]
    html_cards = "".join(
        f'<div class="feature-card"><span class="lamp {state}"></span><div>'
        f"<strong>{html.escape(name)}</strong><b>{html.escape(status)}</b>"
        f"<small>{html.escape(detail)}</small></div></div>"
        for name, status, detail, state in cards
    )
    return f"""
    <section class="page-title"><span class="eyebrow">FEATURE GOVERNANCE</span><h1>Evidence map</h1>
      <p>Maximum credible inputs, minimum unsupported assumptions. Raw data is retained; model admission stays evidence-driven.</p>
    </section>
    <div class="feature-grid">{html_cards}</div>
    """


def render_dashboard(snapshot: dict[str, Any], *, tab: str = "overview") -> str:
    tabs = {
        "overview": ("Overview", _overview),
        "research": ("Research", _research),
        "performance": ("Performance", _performance),
        "coverage": ("Coverage", _coverage),
        "health": ("Health", _health),
        "features": ("Features", _features),
    }
    if tab not in tabs:
        tab = "overview"
    nav = "".join(
        f'<a href="/?tab={key}" class="{"active" if key == tab else ""}">{label}</a>'
        for key, (label, _) in tabs.items()
    )
    body = tabs[tab][1](snapshot)
    generated = html.escape(snapshot.get("generated_at") or "—")
    css = """
    :root{--bg:#0b1118;--panel:#111a24;--panel2:#151f2a;--line:#263341;--text:#edf1f4;
    --muted:#8ea0b2;--cream:#eee6d5;--red:#b85450;--green:#51b786;--amber:#d6a65a;--blue:#6e9fca}
    *{box-sizing:border-box} body{margin:0;background:radial-gradient(circle at 85% 0,#182633 0,#0b1118 34%);
    color:var(--text);font:14px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    a{color:inherit;text-decoration:none}.shell{max-width:1480px;margin:auto;padding:22px 28px 48px}
    header{display:flex;align-items:center;gap:28px;padding:10px 2px 24px;border-bottom:1px solid var(--line)}
    .brand{display:flex;align-items:center;gap:11px;font-weight:800;letter-spacing:.02em}.brand-mark{width:34px;height:34px;
    display:grid;place-items:center;border:1px solid #3a4958;border-radius:11px;background:#101923;color:var(--cream)}
    nav{display:flex;gap:6px;flex-wrap:wrap}nav a{padding:8px 12px;color:var(--muted);border-radius:8px}nav a:hover{background:#17222d;color:var(--text)}
    nav a.active{background:#202c38;color:var(--cream)}.read-only{margin-left:auto;color:var(--green);font-size:12px;font-weight:700}
    main{padding-top:24px}.hero,.page-title{display:flex;justify-content:space-between;align-items:center;margin:4px 0 22px}
    .hero h1,.page-title h1{font-size:34px;line-height:1.1;margin:4px 0 8px;letter-spacing:-.03em}.hero p,.page-title p{color:var(--muted);max-width:780px;margin:0}
    .hero-mark{font-size:45px;filter:grayscale(.35);opacity:.72}.eyebrow{font-size:11px;font-weight:800;letter-spacing:.15em;color:#a7b7c6}
    .lamps{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin-bottom:14px}
    .lamp-card,.feature-card{display:flex;align-items:center;gap:11px;background:linear-gradient(180deg,#131d27,#101820);border:1px solid var(--line);border-radius:12px;padding:13px}
    .lamp{width:9px;height:9px;border-radius:50%;flex:0 0 auto;background:#607080;box-shadow:0 0 0 3px #202b35}.lamp.green{background:var(--green);box-shadow:0 0 0 3px #17392c}
    .lamp.amber{background:var(--amber);box-shadow:0 0 0 3px #3c3020}.lamp.red{background:#d76767;box-shadow:0 0 0 3px #432121}.lamp.muted{background:#66727d}
    .lamp-card strong,.feature-card strong{display:block}.lamp-card small,.feature-card small{display:block;color:var(--muted);margin-top:2px}
    .metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:16px}.metrics.compact{margin:0}
    .metric-card{min-height:92px;background:linear-gradient(180deg,#15202a,#111922);border:1px solid var(--line);border-radius:12px;padding:14px}
    .metric-card span{display:block;color:var(--muted);font-size:12px}.metric-card strong{display:block;font-size:25px;margin-top:9px;color:var(--cream);letter-spacing:-.02em}
    .metric-card small{display:block;color:var(--muted);margin-top:3px}.panel{background:linear-gradient(180deg,#111a24,#0f171f);border:1px solid var(--line);border-radius:14px;padding:17px;margin:0 0 14px;overflow:hidden}
    .panel-head{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:12px}.panel h2{font-size:16px;margin:0}
    .tag{font-size:10px;font-weight:800;letter-spacing:.09em;color:#a8b6c2;border:1px solid #344251;background:#19232d;border-radius:999px;padding:5px 8px}
    .tag.good{color:#8bd8b3;border-color:#315d49}.tag.warn{color:#e5bc78;border-color:#655035}.two-col{display:grid;grid-template-columns:1fr 1fr;gap:14px}
    .facts{display:grid;grid-template-columns:minmax(130px,1fr) 1.4fr;gap:8px 16px;margin:0}.facts dt{color:var(--muted)}.facts dd{margin:0;text-align:right;word-break:break-word}
    table{width:100%;border-collapse:collapse;font-size:12px}th{text-align:left;color:#90a2b3;font-weight:700;padding:9px 9px;border-bottom:1px solid var(--line);white-space:nowrap}
    td{padding:10px 9px;border-bottom:1px solid #1f2a35;vertical-align:top}tr:last-child td{border-bottom:0}.table-wrap{overflow:auto}.empty{text-align:center;color:var(--muted);padding:28px}
    .muted{color:var(--muted)}.feature-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:10px}
    .feature-card b{display:block;font-size:11px;letter-spacing:.08em;color:var(--cream);margin:2px 0}.footer{margin-top:22px;color:#718292;font-size:11px;display:flex;justify-content:space-between}
    @media(max-width:800px){.shell{padding:14px}header{align-items:flex-start;flex-direction:column;gap:12px}.read-only{margin-left:0}.two-col{grid-template-columns:1fr}.hero-mark{display:none}.hero h1,.page-title h1{font-size:29px}}
    """
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="60">
    <title>QuantBet Baseball</title><style>{css}</style></head><body><div class="shell">
    <header><div class="brand"><span class="brand-mark">QB</span><span>QuantBet Baseball</span></div>
    <nav>{nav}</nav><span class="read-only">● READ ONLY</span></header><main>{body}</main>
    <div class="footer"><span>Durable PostgreSQL evidence only · no provider calls</span><span>Generated {generated}</span></div>
    </div></body></html>"""


@dataclass(frozen=True, slots=True)
class DashboardConfig:
    host: str = "0.0.0.0"
    port: int = 8080


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "QuantBetBaseballDashboard/1.0"

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/livez":
            try:
                with psycopg.connect(database_url_from_env(), autocommit=True) as connection:
                    _query_one(connection, "SELECT 1 AS ok")
                payload = json.dumps({"status": "ok", "database": "ok"}).encode()
                self._send(HTTPStatus.OK, "application/json; charset=utf-8", payload)
            except Exception:
                payload = json.dumps({"status": "degraded", "database": "down"}).encode()
                self._send(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    "application/json; charset=utf-8",
                    payload,
                )
            return

        if parsed.path == "/api/snapshot":
            try:
                snapshot = build_dashboard_snapshot()
                payload = json.dumps(
                    snapshot,
                    default=_iso,
                    separators=(",", ":"),
                ).encode()
                self._send(HTTPStatus.OK, "application/json; charset=utf-8", payload)
            except Exception as exc:
                payload = json.dumps(
                    {"status": "error", "type": type(exc).__name__},
                    separators=(",", ":"),
                ).encode()
                self._send(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    "application/json; charset=utf-8",
                    payload,
                )
            return

        if parsed.path != "/":
            self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"Not found")
            return

        query = parse_qs(parsed.query)
        tab = (query.get("tab") or ["overview"])[0]
        try:
            snapshot = build_dashboard_snapshot()
            body = render_dashboard(snapshot, tab=tab).encode("utf-8")
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", body)
        except Exception as exc:
            message = (
                "<!doctype html><meta charset='utf-8'><title>Dashboard unavailable</title>"
                "<body style='background:#0b1118;color:#edf1f4;font-family:system-ui;padding:32px'>"
                "<h1>Dashboard unavailable</h1>"
                f"<p>Read-only data source error: {html.escape(type(exc).__name__)}</p>"
                "</body>"
            ).encode()
            self._send(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "text/html; charset=utf-8",
                message,
            )

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    port = int(os.getenv("PORT", "8080").strip() or "8080")
    server = ThreadingHTTPServer(("0.0.0.0", port), DashboardHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
