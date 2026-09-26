# QuantBet Baseball Operations Dashboard

## Purpose

The Baseball dashboard is a **read-only control plane** over durable PostgreSQL evidence.

It answers, at a glance:

- Is the worker alive and fresh?
- Is PostgreSQL reachable?
- Is the API credential configured?
- Is the raw archive configured?
- Are migrations current?
- Is paper mode on?
- Is collection intentionally locked or enabled?
- Has the bounded acceptance canary passed?
- Are fixture and odds observations fresh?
- How much API budget/headroom exists?
- How far has the lifecycle progressed from fixture evidence through settlement/CLV?
- What paper research performance exists?
- What immutable picks were registered, closed and settled?

The dashboard must never create a false green state. A status is green only when the required durable evidence is present and fresh.

## Service boundary

The dashboard runs as a **separate Railway service** from the Baseball cron worker.

It:

- reads PostgreSQL;
- exposes HTML plus health/readiness endpoints;
- does not compose the API-Sports client;
- does not require API_BASEBALL_KEY;
- does not poll API-Sports;
- cannot consume the Baseball provider request budget;
- performs no lifecycle writes;
- performs no bet execution;
- keeps the worker service and cron unchanged.

## Routes

- `/` — dashboard UI
- `/dashboard` — dashboard UI
- `/livez` — process liveness
- `/readyz` — PostgreSQL readiness
- `/api/status` — read-only JSON projection

All POST requests are rejected.

## Views

### System

Evidence-driven status board:

- dashboard process;
- worker freshness;
- PostgreSQL;
- API credential configuration from activation-gate evidence;
- raw archive configuration;
- migration state;
- paper mode;
- collection state;
- canary state;
- fixture freshness;
- odds freshness;
- API request budget/headroom;
- latest canary evidence;
- lifecycle row counts.

Collection OFF during acceptance is rendered as **LOCKED**, not as a crash.

A failed/not-yet-passed canary is amber until acceptance evidence proves otherwise.

Missing/freshness-failed odds evidence is red because the model cannot produce an executable pick without market evidence.

### Research

Reads existing database performance views:

- settled picks;
- W/L/P;
- ROI;
- Brier score;
- log loss;
- CLV coverage;
- positive CLV rate;
- average CLV;
- model-version/bookmaker breakdown.

Migration 008 makes the fixed 300 RSD paper stake canonical database evidence. The dashboard reads `settled_stake_minor` and `realized_profit_minor` from PostgreSQL instead of deriving monetary P/L in the frontend.

### History

Immutable paper-pick ledger:

- fixture;
- league;
- selection;
- executable bookmaker;
- entry odds;
- model probability;
- market probability;
- edge;
- EV;
- lifecycle state;
- settlement;
- derived 300 RSD paper P/L;
- CLV.

When no registered picks exist, the dashboard shows an explicit empty state rather than demo/fake data.

## Visual language

The UI uses a restrained Baseball identity:

- charcoal/deep navy control-plane background;
- warm off-white baseball accent;
- muted seam-red highlight;
- health green / warning amber / failure red;
- restrained blue for intentional locked/neutral states;
- subtle baseball iconography only;
- no sportsbook/casino visual treatment;
- no aggressive baseball artwork;
- dense operational tables remain the priority.

## Freshness policy

Initial dashboard thresholds:

- worker stale after 35 minutes, reflecting the 15-minute cron cadence with bounded tolerance;
- fixture evidence warning after 24 hours;
- odds evidence stale after 6 hours.

These are dashboard interpretation thresholds only. They do not change backend eligibility, quote-age or decision policies.

## Playable bookmaker boundary

Only:

- Bet365;
- 1xBet

are shown as executable bookmaker identities.

Other bookmakers may exist in market-intelligence evidence but cannot become a RegisteredPick because the domain layer independently enforces the same rule.

## Integrity

1. PostgreSQL remains authoritative.
2. UI refresh does not trigger provider calls.
3. No fabricated odds/probabilities/health/picks/results.
4. Missing data stays visibly missing.
5. Dashboard state never changes worker or betting state.
6. Football/QuantBet production dashboard is a read-only functional reference only; no Football code is modified.
