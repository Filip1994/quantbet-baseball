"""Read-only QuantBet Baseball operations and research dashboard."""

from __future__ import annotations

import base64
import hmac
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlsplit

import psycopg
from psycopg.rows import dict_row

from .postgres_repository import PostgreSQLEvidenceRepository

WORKER_FRESHNESS = timedelta(minutes=35)
FIXTURE_FRESHNESS = timedelta(hours=24)
ODDS_FRESHNESS = timedelta(hours=6)
PAPER_STAKE_RSD = 300


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return str(value) if value is not None else None


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _age(now: datetime, raw: Any) -> timedelta | None:
    if raw is None:
        return None
    stamp = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        return None
    return now - stamp.astimezone(UTC)


def _fmt_age(age: timedelta | None) -> str:
    if age is None:
        return "no evidence"
    seconds = max(0, int(age.total_seconds()))
    if seconds < 90:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 90:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


@dataclass(frozen=True, slots=True)
class StatusItem:
    label: str
    state: str
    value: str
    detail: str = ""


class BaseballDashboardRepository:
    """Read durable Baseball state without mutating or calling providers."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def check_database(self) -> bool:
        try:
            with psycopg.connect(self.database_url) as connection:
                connection.execute("SELECT 1")
            return True
        except Exception:  # noqa: BLE001 - readiness must fail closed
            return False

    def snapshot(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        with psycopg.connect(self.database_url) as evidence_connection:
            evidence = PostgreSQLEvidenceRepository(evidence_connection)
            health = evidence.health_snapshot()

        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            runtime = connection.execute(
                """
                SELECT run_id, started_at, finished_at, collection_enabled,
                       mode, status, stats
                FROM runtime_cycles
                ORDER BY finished_at DESC, run_id DESC
                LIMIT 1
                """
            ).fetchone()

            gates = connection.execute(
                """
                SELECT DISTINCT ON (target)
                       target, assessed_at, verdict, reason_codes,
                       daily_request_budget, cycle_request_cap,
                       cron_interval_minutes, cycles_per_day,
                       worst_case_daily_requests, request_headroom,
                       daily_reserve_required, paper_mode,
                       collection_enabled, api_key_configured,
                       raw_archive_configured, migrations_current,
                       runtime_fresh, canary_passed, latest_canary_id
                FROM activation_gate_assessments
                ORDER BY target, assessed_at DESC, assessment_id DESC
                """
            ).fetchall()

            canary = connection.execute(
                """
                SELECT canary_id, started_at, finished_at, status,
                       max_api_requests, api_requests,
                       fixture_observations_inserted, observations_inserted,
                       errors, archive_verified, db_write_verified,
                       reason_codes
                FROM operational_canary_runs
                ORDER BY finished_at DESC, canary_id DESC
                LIMIT 1
                """
            ).fetchone()

            performance = connection.execute(
                "SELECT * FROM baseball_moneyline_performance"
            ).fetchone()
            money = connection.execute(
                "SELECT settled_stake_minor, realized_profit_minor "
                "FROM baseball_moneyline_dashboard"
            ).fetchone()
            breakdown = connection.execute(
                """
                SELECT dimension, dimension_value, settled_picks,
                       realized_profit_per_unit, roi_per_unit_staked,
                       brier_score, log_loss, average_clv_probability_delta
                FROM baseball_moneyline_performance_breakdown
                ORDER BY dimension, settled_picks DESC, dimension_value
                """
            ).fetchall()

            picks = connection.execute(
                """
                WITH latest_fixture AS (
                    SELECT DISTINCT ON (game_id)
                           game_id, league, home_team_name, away_team_name,
                           kickoff_at, provider_status
                    FROM fixture_observations
                    ORDER BY game_id, observed_at DESC,
                             fixture_observation_id DESC
                )
                SELECT r.pick_id, r.game_id, f.league,
                       f.home_team_name, f.away_team_name,
                       r.selection, r.bookmaker, r.entry_odds,
                       r.model_probability, r.market_probability,
                       r.fair_decimal_odds, r.edge,
                       r.expected_value_per_unit, r.uncertainty_metric,
                       r.model_version, r.registered_at, r.kickoff_at,
                       COALESCE(m.state, 'REGISTERED') AS lifecycle_state,
                       c.outcome AS closing_outcome,
                       s.outcome AS settlement_outcome,
                       s.profit_per_unit, s.closing_odds,
                       s.clv_status, s.clv_probability_delta,
                       s.clv_price_ratio, s.settled_at,
                       r.paper_stake_minor, r.currency,
                       CASE
                           WHEN s.settlement_id IS NULL THEN NULL
                           ELSE ROUND(s.profit_per_unit * r.paper_stake_minor)::BIGINT
                       END AS paper_profit_minor
                FROM registered_picks r
                LEFT JOIN latest_fixture f ON f.game_id = r.game_id
                LEFT JOIN pick_monitoring_states m ON m.pick_id = r.pick_id
                LEFT JOIN pick_closing_finalizations c ON c.pick_id = r.pick_id
                LEFT JOIN pick_settlements s ON s.pick_id = r.pick_id
                ORDER BY r.registered_at DESC, r.pick_id DESC
                LIMIT 250
                """
            ).fetchall()

        gate_map = {str(row["target"]): dict(row) for row in gates}
        return {
            "generated_at": now,
            "health": health,
            "runtime": dict(runtime) if runtime else None,
            "gates": gate_map,
            "canary": dict(canary) if canary else None,
            "performance": dict(performance) if performance else {},
            "money": dict(money)
            if money
            else {
                "settled_stake_minor": 0,
                "realized_profit_minor": 0,
            },
            "breakdown": [dict(row) for row in breakdown],
            "picks": [dict(row) for row in picks],
        }


class BaseballDashboard:
    def __init__(self, repository: BaseballDashboardRepository) -> None:
        self.repository = repository

    def snapshot(self) -> dict[str, Any]:
        data = self.repository.snapshot()
        now = data["generated_at"]
        health = data["health"]
        runtime = data["runtime"]
        gate = data["gates"].get("CANARY") or data["gates"].get("SCHEDULED_COLLECTION")

        runtime_age = _age(now, None if runtime is None else runtime["finished_at"])
        fixture_age = _age(now, health.get("latest_fixture_observed_at"))
        odds_age = _age(now, health.get("latest_odds_observed_at"))

        statuses: list[StatusItem] = [
            StatusItem("Dashboard", "good", "ONLINE", "read-only service"),
            StatusItem(
                "Worker",
                "good"
                if runtime_age is not None and runtime_age <= WORKER_FRESHNESS
                else "bad",
                "RUNNING"
                if runtime_age is not None and runtime_age <= WORKER_FRESHNESS
                else "STALE",
                _fmt_age(runtime_age),
            ),
            StatusItem(
                "PostgreSQL",
                "good",
                "CONNECTED",
                f"{health.get('runtime_cycles', 0)} runtime cycles",
            ),
            StatusItem(
                "API credential",
                "good" if gate and gate.get("api_key_configured") else "bad",
                "CONFIGURED" if gate and gate.get("api_key_configured") else "MISSING",
            ),
            StatusItem(
                "Raw archive",
                "good" if gate and gate.get("raw_archive_configured") else "bad",
                "READY" if gate and gate.get("raw_archive_configured") else "MISSING",
            ),
            StatusItem(
                "Migrations",
                "good" if gate and gate.get("migrations_current") else "bad",
                "CURRENT" if gate and gate.get("migrations_current") else "CHECK",
            ),
            StatusItem(
                "Paper mode",
                "good" if gate and gate.get("paper_mode") else "bad",
                "ON" if gate and gate.get("paper_mode") else "OFF",
                f"{PAPER_STAKE_RSD} RSD target singles",
            ),
            StatusItem(
                "Collection",
                "good" if gate and gate.get("collection_enabled") else "locked",
                "ON" if gate and gate.get("collection_enabled") else "LOCKED",
                "intentional until acceptance"
                if not gate or not gate.get("collection_enabled")
                else "scheduled collector enabled",
            ),
            StatusItem(
                "Canary",
                "good" if gate and gate.get("canary_passed") else "warn",
                "PASSED" if gate and gate.get("canary_passed") else "NOT PASSED",
                "acceptance gate",
            ),
            StatusItem(
                "Fixture feed",
                "good"
                if fixture_age is not None and fixture_age <= FIXTURE_FRESHNESS
                else "warn",
                "FRESH"
                if fixture_age is not None and fixture_age <= FIXTURE_FRESHNESS
                else "STALE",
                _fmt_age(fixture_age),
            ),
            StatusItem(
                "Odds evidence",
                "good"
                if odds_age is not None and odds_age <= ODDS_FRESHNESS
                else "bad",
                "FRESH"
                if odds_age is not None and odds_age <= ODDS_FRESHNESS
                else "NO FRESH ODDS",
                _fmt_age(odds_age),
            ),
        ]
        data["statuses"] = statuses
        return data

    def render(self, query: str = "") -> str:
        data = self.snapshot()
        params = parse_qs(query)
        tab = (params.get("tab") or ["system"])[0]
        if tab not in {"system", "research", "history"}:
            tab = "system"

        body = {
            "system": self._system_html,
            "research": self._research_html,
            "history": self._history_html,
        }[tab](data)
        return self._page(data, tab, body)

    def _page(self, data: dict[str, Any], tab: str, body: str) -> str:
        statuses = data["statuses"]
        severe = sum(item.state == "bad" for item in statuses)
        warnings = sum(item.state == "warn" for item in statuses)
        overall = "ATTENTION" if severe or warnings else "HEALTHY"
        overall_class = "bad" if severe else ("warn" if warnings else "good")

        tabs = "".join(
            f'<a class="{"active" if tab == name else ""}" href="/?tab={name}">'
            f"{label}</a>"
            for name, label in (
                ("system", "System"),
                ("research", "Research"),
                ("history", "History"),
            )
        )
        status_strip = "".join(self._status_chip(item) for item in statuses[:6])
        generated = (
            data["generated_at"].astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        )
        return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>QuantBet Baseball</title>
<style>{_CSS}</style>
</head><body>
<div class="shell">
<aside>
  <div class="brand">
    <div class="ball"><i></i><b></b></div>
    <div><strong>QUANTBET</strong><span>BASEBALL LAB</span></div>
  </div>
  <nav>{tabs}</nav>
  <div class="side-note">
    <span>PLAYABLE BOOKS</span>
    <b>Bet365 · 1xBet</b>
    <small>Paper only · {PAPER_STAKE_RSD} RSD singles</small>
  </div>
</aside>
<main>
<header>
  <div><div class="eyebrow">Production research control plane</div>
  <h1>Baseball Operations</h1>
  <p>Evidence-backed health, research lifecycle and paper performance.</p></div>
  <div class="overall {overall_class}"><span></span><div><small>SYSTEM</small><b>{overall}</b></div></div>
</header>
<section class="status-strip">{status_strip}</section>
{body}
<footer><span>Auto-refresh 30s · PostgreSQL is authoritative · dashboard makes no provider calls</span><span>{generated}</span></footer>
</main></div></body></html>"""

    def _system_html(self, data: dict[str, Any]) -> str:
        health = data["health"]
        gate = data["gates"].get("CANARY") or {}
        canary = data.get("canary") or {}
        statuses = "".join(
            f"""<article class="health-card {item.state}">
            <div class="health-head"><span class="dot"></span><b>{escape(item.label)}</b></div>
            <strong>{escape(item.value)}</strong><small>{escape(item.detail or "—")}</small>
            </article>"""
            for item in data["statuses"]
        )
        lifecycle = [
            ("Fixtures", health.get("distinct_fixtures", 0)),
            ("Fixture obs", health.get("fixture_observations", 0)),
            ("Odds obs", health.get("odds_observations", 0)),
            ("Quote games", health.get("distinct_quote_games", 0)),
            ("Predictions", health.get("model_predictions", 0)),
            ("Evaluations", health.get("value_evaluations", 0)),
            ("Final checks", health.get("final_quote_verifications", 0)),
            ("Picks", health.get("registered_picks", 0)),
            ("Monitoring", health.get("monitored_picks", 0)),
            ("Closings", health.get("closing_finalizations", 0)),
            ("Settled", health.get("settled_picks", 0)),
            ("CLV available", health.get("clv_available", 0)),
        ]
        lifecycle_html = "".join(
            f'<div class="metric"><small>{escape(k)}</small><b>{v}</b></div>'
            for k, v in lifecycle
        )
        provider_evidence = [
            (
                "Standings",
                health.get("standing_snapshots", 0),
                health.get("latest_standings_observed_at"),
            ),
            (
                "Team stats",
                health.get("team_statistics_snapshots", 0),
                health.get("latest_team_statistics_observed_at"),
            ),
            (
                "Catalogs",
                health.get("reference_catalog_snapshots", 0),
                health.get("latest_catalog_observed_at"),
            ),
            (
                "Game history",
                health.get("game_history_snapshots", 0),
                health.get("latest_game_history_observed_at"),
            ),
            (
                "MLB enrich",
                health.get("official_mlb_pregame_snapshots", 0),
                health.get("latest_official_mlb_observed_at"),
            ),
        ]
        provider_html = "".join(
            f'<div class="metric"><small>{escape(label)}</small><b>{count}</b>'
            f"<span>{escape(_fmt_age(_age(data['generated_at'], stamp)))}</span></div>"
            for label, count, stamp in provider_evidence
        )
        reasons = gate.get("reason_codes") or []
        reason_html = (
            "".join(f"<span>{escape(str(x))}</span>" for x in reasons)
            if reasons
            else '<span class="ok">NO BLOCKER CODES</span>'
        )
        budget = {
            "Daily budget": gate.get("daily_request_budget", "—"),
            "Cycle cap": gate.get("cycle_request_cap", "—"),
            "Worst/day": gate.get("worst_case_daily_requests", "—"),
            "Headroom": gate.get("request_headroom", "—"),
            "Reserve": gate.get("daily_reserve_required", "—"),
        }
        budget_html = "".join(
            f"<div><small>{escape(k)}</small><b>{escape(str(v))}</b></div>"
            for k, v in budget.items()
        )
        canary_reasons = canary.get("reason_codes") or []
        canary_reason = ", ".join(str(x) for x in canary_reasons) or "—"
        runtime = data.get("runtime") or {}
        cycle = runtime.get("stats") or {}
        requests = int(cycle.get("api_requests") or 0)
        cap = int(cycle.get("cycle_request_cap") or 0)
        selected = int(cycle.get("games_selected") or 0)
        due = int(cycle.get("due_events") or 0)
        not_due = int(cycle.get("not_due_events") or 0)
        odds_calls = int(cycle.get("odds_calls") or 0)
        inserts = int(cycle.get("observations_inserted") or 0)
        efficiency = inserts / requests if requests else None
        efficiency_text = f"{efficiency:.2f}" if efficiency is not None else "—"
        cycle_items = [
            ("Requests", f"{requests} / {cap}" if cap else str(requests)),
            ("Due games", due),
            ("Selected", selected),
            ("Not due", not_due),
            ("Odds calls", odds_calls),
            ("Obs / request", efficiency_text),
        ]
        cycle_html = "".join(
            f"<div><small>{escape(str(label))}</small><b>{escape(str(value))}</b></div>"
            for label, value in cycle_items
        )
        return f"""
<section class="section-title"><div><small>CONTROL PLANE</small><h2>System health</h2></div>
<span>Every green light requires durable evidence.</span></section>
<div class="health-grid">{statuses}</div>
<section class="split">
  <article class="panel">
    <div class="panel-title"><b>Lifecycle telemetry</b><span>PostgreSQL counts</span></div>
    <div class="metric-grid">{lifecycle_html}</div>
  </article>
  <article class="panel">
    <div class="panel-title"><b>API budget guard</b><span>no blind burn</span></div>
    <div class="budget-grid">{budget_html}</div>
    <div class="reason-box"><small>Activation gate</small>
      <b>{escape(str(gate.get("verdict", "UNKNOWN")))}</b>
      <div>{reason_html}</div>
    </div>
  </article>
</section>
<section class="panel table-panel">
  <div class="panel-title"><b>Primary provider evidence</b><span>durable counts · freshness</span></div>
  <div class="metric-grid">{provider_html}</div>
</section>
<section class="panel">
  <div class="panel-title"><b>Latest collection efficiency</b><span>scheduler-aware request use</span></div>
  <div class="budget-grid cycle-grid">{cycle_html}</div>
  <p class="muted">Selected should never exceed due after cadence repair. Not-due games remain visible without consuming broad odds requests.</p>
</section>
<section class="panel">
  <div class="panel-title"><b>Latest bounded canary</b><span>{escape(str(canary.get("finished_at") or "no canary evidence"))}</span></div>
  <div class="canary-row">
    <div><small>Status</small><b>{escape(str(canary.get("status") or "NONE"))}</b></div>
    <div><small>Requests</small><b>{escape(str(canary.get("api_requests", 0)))} / {escape(str(canary.get("max_api_requests", "—")))}</b></div>
    <div><small>Odds writes</small><b>{escape(str(canary.get("observations_inserted", 0)))}</b></div>
    <div><small>Archive</small><b>{escape(str(canary.get("archive_verified", False)))}</b></div>
    <div><small>DB writes</small><b>{escape(str(canary.get("db_write_verified", False)))}</b></div>
  </div>
  <p class="muted">Reason codes: {escape(canary_reason)}</p>
</section>"""

    def _research_html(self, data: dict[str, Any]) -> str:
        p = data.get("performance") or {}
        settled = int(p.get("settled_picks") or 0)
        money = data.get("money") or {}
        realized_minor = int(money.get("realized_profit_minor") or 0)
        settled_stake_minor = int(money.get("settled_stake_minor") or 0)
        paper_profit = realized_minor / 100
        settled_stake = settled_stake_minor / 100
        health = data.get("health") or {}
        provider_summary = (
            f"Standings {health.get('distinct_standing_teams', 0)} teams · "
            f"team stats {health.get('distinct_team_statistics_teams', 0)} teams · "
            f"history {health.get('distinct_game_history_games', 0)} games · "
            f"MLB enrichment {health.get('official_mlb_pregame_snapshots', 0)} snapshots"
        )
        cards = [
            ("Settled", settled, ""),
            (
                "W / L / P",
                f"{p.get('wins', 0)} / {p.get('losses', 0)} / {p.get('pushes', 0)}",
                "",
            ),
            ("ROI", self._pct(p.get("roi_per_unit_staked")), ""),
            ("Paper P/L", f"{paper_profit:+.0f} RSD", "DB-backed"),
            ("CLV coverage", self._pct(p.get("clv_coverage")), ""),
            ("Positive CLV", self._pct(p.get("positive_clv_rate")), ""),
            ("Brier", self._dec(p.get("brier_score")), ""),
            (
                "Log loss",
                self._dec(p.get("log_loss")),
                f"settled stake {settled_stake:.0f} RSD",
            ),
        ]
        cards_html = "".join(
            f'<article class="kpi"><small>{escape(str(label))}</small><b>{escape(str(value))}</b><span>{escape(note)}</span></article>'
            for label, value, note in cards
        )
        rows = data.get("breakdown") or []
        row_html = (
            "".join(
                f"""<tr><td>{escape(str(r.get("dimension")))}</td>
            <td><b>{escape(str(r.get("dimension_value")))}</b></td>
            <td>{r.get("settled_picks", 0)}</td>
            <td>{self._pct(r.get("roi_per_unit_staked"))}</td>
            <td>{self._dec(r.get("brier_score"))}</td>
            <td>{self._dec(r.get("log_loss"))}</td>
            <td>{self._pct(r.get("average_clv_probability_delta"))}</td></tr>"""
                for r in rows
            )
            or '<tr><td class="empty" colspan="7">No settled research picks yet.</td></tr>'
        )
        return f"""
<section class="section-title"><div><small>RESEARCH</small><h2>Paper performance</h2></div>
<span>Moneyline closed loop · full-game totals next</span></section>
<div class="kpi-grid">{cards_html}</div>
<section class="panel table-panel">
<div class="panel-title"><b>Performance breakdown</b><span>model / bookmaker</span></div>
<div class="table-wrap"><table><thead><tr><th>Dimension</th><th>Value</th><th>N</th><th>ROI</th><th>Brier</th><th>Log loss</th><th>Avg CLV Δ</th></tr></thead>
<tbody>{row_html}</tbody></table></div></section>
<section class="research-note">
<b>Primary evidence coverage</b>
<p>{escape(provider_summary)}</p>
<b>Feature universe</b>
<p>MLB target includes starting pitcher, bullpen, injuries/roster, confirmed lineup, Statcast, park/roof, weather, rest/travel/time-of-day and market evidence — admitted only after point-in-time validation. Other leagues use only verified available fields.</p>
<div><span>PLAYABLE</span><strong>Bet365 · 1xBet</strong></div>
</section>"""

    def _history_html(self, data: dict[str, Any]) -> str:
        rows = data.get("picks") or []
        body = "".join(self._pick_row(row) for row in rows)
        if not body:
            body = '<tr><td class="empty" colspan="12">No registered paper picks yet. The system is correctly waiting for accepted odds evidence.</td></tr>'
        return f"""
<section class="section-title"><div><small>HISTORY</small><h2>Paper pick ledger</h2></div>
<span>immutable entry → close → result → CLV</span></section>
<section class="panel table-panel"><div class="panel-title"><b>Registered picks</b><span>{len(rows)} rows</span></div>
<div class="table-wrap"><table><thead><tr>
<th>Game</th><th>Pick</th><th>Book</th><th>Entry</th><th>Model p</th><th>Market p</th>
<th>Edge</th><th>EV</th><th>State</th><th>Result</th><th>P/L</th><th>CLV</th>
</tr></thead><tbody>{body}</tbody></table></div></section>"""

    def _pick_row(self, row: dict[str, Any]) -> str:
        home = row.get("home_team_name") or "Home"
        away = row.get("away_team_name") or "Away"
        result = row.get("settlement_outcome") or "PENDING"
        paper_profit_minor = row.get("paper_profit_minor")
        pnl = (
            "—"
            if paper_profit_minor is None
            else f"{int(paper_profit_minor) / 100:+.0f} RSD"
        )
        clv = self._pct(row.get("clv_probability_delta"))
        bookmaker = str(row.get("bookmaker") or "—")
        book_class = "bet365" if "365" in bookmaker.casefold() else "one-x"
        return f"""<tr>
<td><b>{escape(str(away))} @ {escape(str(home))}</b><small>{escape(str(row.get("league") or "—"))}</small></td>
<td>{escape(str(row.get("selection") or "—").upper())}</td>
<td><span class="book {book_class}">{escape(bookmaker)}</span></td>
<td>{self._odds(row.get("entry_odds"))}</td>
<td>{self._pct(row.get("model_probability"))}</td>
<td>{self._pct(row.get("market_probability"))}</td>
<td>{self._pct(row.get("edge"))}</td>
<td>{self._pct(row.get("expected_value_per_unit"))}</td>
<td><span class="pill">{escape(str(row.get("lifecycle_state") or "—"))}</span></td>
<td><span class="result {escape(str(result).casefold())}">{escape(str(result))}</span></td>
<td>{escape(pnl)}</td><td>{clv}</td></tr>"""

    @staticmethod
    def _status_chip(item: StatusItem) -> str:
        return (
            f'<div class="status {item.state}"><span></span><div><small>'
            f"{escape(item.label)}</small><b>{escape(item.value)}</b></div></div>"
        )

    @staticmethod
    def _pct(value: Any) -> str:
        number = _number(value)
        return "—" if number is None else f"{number * 100:+.2f}%"

    @staticmethod
    def _dec(value: Any) -> str:
        number = _number(value)
        return "—" if number is None else f"{number:.4f}"

    @staticmethod
    def _odds(value: Any) -> str:
        number = _number(value)
        return "—" if number is None else f"{number:.2f}"


class BaseballDashboardHTTPService:
    def __init__(
        self,
        dashboard: BaseballDashboard,
        *,
        host: str,
        port: int,
    ) -> None:
        service = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlsplit(self.path)
                if parsed.path == "/livez":
                    service._text(self, 200, "ok\n", "text/plain; charset=utf-8")
                    return
                if parsed.path == "/readyz":
                    try:
                        dashboard.snapshot()
                        service._text(
                            self,
                            200,
                            "ready\n",
                            "text/plain; charset=utf-8",
                        )
                    except Exception as exc:  # noqa: BLE001
                        service._text(
                            self,
                            503,
                            f"snapshot_unavailable:{type(exc).__name__}\n",
                            "text/plain; charset=utf-8",
                        )
                    return
                if parsed.path == "/api/status":
                    if not service._authorize(self):
                        return
                    try:
                        payload = dashboard.snapshot()
                        safe = service._json_safe(payload)
                        service._text(
                            self,
                            200,
                            json.dumps(safe, separators=(",", ":")) + "\n",
                            "application/json; charset=utf-8",
                        )
                    except Exception as exc:  # noqa: BLE001
                        service._text(
                            self,
                            503,
                            type(exc).__name__ + "\n",
                            "text/plain; charset=utf-8",
                        )
                    return
                if parsed.path not in {"/", "/dashboard"}:
                    service._text(self, 404, "not_found\n", "text/plain; charset=utf-8")
                    return
                if not service._authorize(self):
                    return
                try:
                    service._text(
                        self,
                        200,
                        dashboard.render(parsed.query),
                        "text/html; charset=utf-8",
                    )
                except Exception as exc:  # noqa: BLE001
                    service._text(
                        self,
                        503,
                        type(exc).__name__ + "\n",
                        "text/plain; charset=utf-8",
                    )

            def do_POST(self) -> None:
                service._text(self, 405, "read_only\n", "text/plain; charset=utf-8")

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self._server = ThreadingHTTPServer((host, port), Handler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, StatusItem):
            return {
                "label": value.label,
                "state": value.state,
                "value": value.value,
                "detail": value.detail,
            }
        if isinstance(value, dict):
            return {
                str(key): BaseballDashboardHTTPService._json_safe(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [BaseballDashboardHTTPService._json_safe(item) for item in value]
        return value

    @staticmethod
    def _text(
        handler: BaseHTTPRequestHandler,
        status: int,
        body: str,
        content_type: str,
    ) -> None:
        encoded = body.encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Cache-Control", "no-store")
        handler.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'",
        )
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("X-Frame-Options", "DENY")
        handler.send_header("Content-Length", str(len(encoded)))
        handler.end_headers()
        handler.wfile.write(encoded)

    @staticmethod
    def _authorize(handler: BaseHTTPRequestHandler) -> bool:
        public = os.getenv("BASEBALL_DASHBOARD_PUBLIC", "").strip().casefold()
        if public in {"1", "true", "yes", "on"}:
            return True
        password = os.getenv("BASEBALL_DASHBOARD_PASSWORD", "")
        username = os.getenv("BASEBALL_DASHBOARD_USER", "quantbet")
        if not password:
            BaseballDashboardHTTPService._text(
                handler, 404, "not_found\n", "text/plain; charset=utf-8"
            )
            return False
        supplied_user = supplied_password = ""
        header = handler.headers.get("Authorization", "")
        if header.startswith("Basic "):
            try:
                decoded = base64.b64decode(header[6:], validate=True).decode()
                supplied_user, supplied_password = decoded.split(":", 1)
            except (ValueError, UnicodeDecodeError):
                pass
        if hmac.compare_digest(supplied_user, username) and hmac.compare_digest(
            supplied_password, password
        ):
            return True
        encoded = b"authentication_required\n"
        handler.send_response(401)
        handler.send_header("WWW-Authenticate", 'Basic realm="QuantBet Baseball"')
        handler.send_header("Content-Type", "text/plain; charset=utf-8")
        handler.send_header("Content-Length", str(len(encoded)))
        handler.end_headers()
        handler.wfile.write(encoded)
        return False

    def start(self) -> None:
        self._thread.start()

    def serve_forever(self) -> None:
        self._server.serve_forever()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread.is_alive():
            self._thread.join(timeout=5)


_CSS = """
:root{--bg:#0e1519;--panel:#151f24;--panel2:#19262c;--line:#2a3940;--text:#edf1ed;--muted:#87979b;--cream:#e7dfcd;--green:#69c18c;--amber:#dfb85e;--red:#db737a;--blue:#78a7bf;--seam:#9e4b51}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 85% 0,#182a31 0,transparent 32%),var(--bg);color:var(--text);font:14px Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.shell{display:grid;grid-template-columns:220px minmax(0,1fr);min-height:100vh}aside{border-right:1px solid var(--line);padding:22px 16px;background:rgba(10,17,20,.86);position:sticky;top:0;height:100vh}
.brand{display:flex;align-items:center;gap:11px;margin:2px 3px 30px}.brand strong{font-size:14px;letter-spacing:.08em}.brand div>span{display:block;font-size:9px;color:var(--muted);letter-spacing:.16em;margin-top:3px}.ball{width:34px;height:34px;border-radius:50%;background:var(--cream);position:relative;box-shadow:0 4px 18px #0008}.ball:before,.ball:after{content:"";position:absolute;top:5px;width:13px;height:24px;border:2px solid var(--seam);border-top-color:transparent;border-bottom-color:transparent;border-radius:50%}.ball:before{left:4px;transform:rotate(-18deg)}.ball:after{right:4px;transform:rotate(18deg)}
nav{display:grid;gap:7px}nav a{color:#9eacaf;text-decoration:none;padding:11px 12px;border-radius:9px;font-weight:750;border:1px solid transparent}nav a:hover{background:#162329;color:white}nav a.active{background:#1b2c33;color:var(--cream);border-color:#31454d;box-shadow:inset 3px 0 var(--seam)}
.side-note{position:absolute;bottom:20px;left:16px;right:16px;padding:13px;border:1px solid var(--line);border-radius:11px;background:#121c21}.side-note span{font-size:9px;color:var(--muted);letter-spacing:.13em}.side-note b{display:block;margin:7px 0;color:var(--cream)}.side-note small{color:#718388}
main{min-width:0;padding:25px 30px 18px;max-width:1680px;width:100%;margin:auto}header{display:flex;align-items:center;justify-content:space-between;gap:18px;margin-bottom:17px}.eyebrow{font-size:10px;color:#84979b;letter-spacing:.14em;text-transform:uppercase;font-weight:850}h1{margin:3px 0 2px;font-size:27px;letter-spacing:-.03em}header p{margin:0;color:var(--muted);font-size:12px}.overall{display:flex;align-items:center;gap:9px;padding:10px 14px;border-radius:11px;border:1px solid var(--line);background:#131e23}.overall>span,.status>span,.health-head .dot{width:8px;height:8px;border-radius:50%;background:currentColor;box-shadow:0 0 0 4px rgba(255,255,255,.025)}.overall small,.status small{display:block;color:#7f9094;font-size:8px;letter-spacing:.13em}.overall b,.status b{font-size:11px;letter-spacing:.04em}.good{color:var(--green)!important}.warn{color:var(--amber)!important}.bad{color:var(--red)!important}.locked{color:var(--blue)!important}
.status-strip{display:grid;grid-template-columns:repeat(6,minmax(125px,1fr));gap:7px;margin-bottom:23px}.status{display:flex;align-items:center;gap:9px;padding:9px 11px;border:1px solid var(--line);background:#121c21;border-radius:9px}.status div{color:var(--text)}
.section-title{display:flex;align-items:end;justify-content:space-between;margin:22px 0 11px}.section-title small{font-size:9px;letter-spacing:.15em;color:var(--seam);font-weight:900}.section-title h2{margin:2px 0 0;font-size:18px}.section-title>span{font-size:11px;color:var(--muted)}
.health-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.health-card{padding:14px;background:linear-gradient(145deg,#172329,#121c21);border:1px solid var(--line);border-radius:12px;min-height:105px}.health-card.good{border-color:#2b5740}.health-card.warn{border-color:#604f2d}.health-card.bad{border-color:#63363a}.health-card.locked{border-color:#345364}.health-head{display:flex;align-items:center;gap:8px;color:var(--text)}.health-head b{font-size:11px}.health-card>strong{display:block;font-size:17px;margin:14px 0 4px;color:currentColor}.health-card>small{color:#7e8e92}
.split{display:grid;grid-template-columns:1.4fr 1fr;gap:11px;margin-top:11px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}.panel-title{display:flex;justify-content:space-between;align-items:center;padding:12px 14px;border-bottom:1px solid var(--line);background:#172329}.panel-title b{font-size:12px}.panel-title span{font-size:10px;color:var(--muted)}.metric-grid{display:grid;grid-template-columns:repeat(4,1fr);padding:11px}.metric{padding:11px;border-right:1px solid #243239;border-bottom:1px solid #243239}.metric small,.budget-grid small,.canary-row small{display:block;color:var(--muted);font-size:9px;text-transform:uppercase;letter-spacing:.06em}.metric b{display:block;font-size:20px;margin-top:5px}.metric span{display:block;color:var(--muted);font-size:9px;margin-top:4px}.budget-grid{display:grid;grid-template-columns:repeat(5,1fr);padding:13px}.budget-grid div{padding:8px}.budget-grid b,.canary-row b{display:block;margin-top:5px}.reason-box{margin:0 13px 13px;padding:11px;border:1px solid #34434a;border-radius:9px;background:#121c21}.reason-box>small{color:var(--muted)}.reason-box>b{float:right}.reason-box div{clear:both;padding-top:9px;display:flex;gap:5px;flex-wrap:wrap}.reason-box span{font-size:9px;background:#2a2420;color:var(--amber);padding:4px 6px;border-radius:5px}.reason-box span.ok{background:#183126;color:var(--green)}
.canary-row{display:grid;grid-template-columns:repeat(5,1fr);padding:14px}.canary-row>div{padding:8px;border-right:1px solid #26343b}.cycle-grid{grid-template-columns:repeat(6,1fr)}.cycle-grid b{font-size:17px}.muted{color:var(--muted);font-size:10px;padding:0 14px 12px}
.kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.kpi{background:linear-gradient(145deg,#172329,#111a1f);border:1px solid var(--line);border-radius:12px;padding:15px}.kpi small{color:var(--muted);text-transform:uppercase;font-size:9px;letter-spacing:.08em}.kpi b{display:block;font-size:22px;margin:7px 0 2px;color:var(--cream)}.kpi span{font-size:9px;color:#718287}
.table-panel{margin-top:11px}.table-wrap{overflow:auto;max-height:64vh}table{border-collapse:separate;border-spacing:0;width:100%;font-size:11px}th,td{padding:10px 12px;border-bottom:1px solid #243239;text-align:left;white-space:nowrap}th{position:sticky;top:0;background:#172329;color:#839397;text-transform:uppercase;font-size:9px;letter-spacing:.07em;z-index:2}tbody tr:hover{background:#1b292f}td small{display:block;color:var(--muted);font-size:9px;margin-top:3px}.empty{text-align:center;padding:45px!important;color:var(--muted)}
.book{display:inline-flex;padding:5px 8px;border-radius:6px;font-weight:900}.book.bet365{background:#176847;color:#f5e36f}.book.one-x{background:#183952;color:#8fc8f3}.pill,.result{display:inline-flex;padding:4px 7px;border-radius:999px;border:1px solid #3b4a50;font-size:9px;font-weight:850}.result.win{color:var(--green);border-color:#38674a}.result.loss{color:var(--red);border-color:#6c3b3e}.result.push{color:var(--blue)}.result.pending{color:var(--amber)}
.research-note{margin-top:11px;border:1px solid #36454b;border-radius:12px;padding:15px;background:linear-gradient(100deg,#172329,#131c20)}.research-note>b{color:var(--cream)}.research-note p{color:#9aabad;max-width:1000px;line-height:1.55}.research-note div{display:flex;align-items:center;gap:9px}.research-note span{font-size:8px;letter-spacing:.12em;color:var(--green)}.research-note strong{font-size:11px}
footer{display:flex;justify-content:space-between;gap:20px;color:#65777b;font-size:10px;margin-top:13px;padding:8px 2px}
@media(max-width:1150px){.status-strip{grid-template-columns:repeat(3,1fr)}.health-grid{grid-template-columns:repeat(2,1fr)}.split{grid-template-columns:1fr}.kpi-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:720px){.shell{display:block}aside{position:relative;height:auto;border-right:0;border-bottom:1px solid var(--line);padding:13px}.brand{margin:0 0 12px}nav{grid-template-columns:repeat(3,1fr)}.side-note{display:none}main{padding:15px}.status-strip{grid-template-columns:repeat(2,1fr)}header{align-items:flex-start}.health-grid{grid-template-columns:1fr}.kpi-grid{grid-template-columns:1fr}.budget-grid,.canary-row{grid-template-columns:repeat(2,1fr)}footer{display:block;line-height:1.7}}
"""
