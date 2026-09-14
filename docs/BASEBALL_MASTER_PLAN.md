# QuantBet Baseball — Master Plan and Execution Layout

**Repository:** `Filip1994/quantbet-baseball`  
**Legacy reference:** `Filip1994/h2h` — read-only reference only  
**Created at:** 2026-09-15 01:05 Europe/Belgrade (UTC+02:00)  
**Last updated:** 2026-09-15  
**Revision:** 3.1  
**Status:** ACTIVE PLAN — evidence architecture and Railway-first persistence direction established

## 0. Operating rule

The project is not considered complete because code, collected data, or research notes exist. A phase is complete only when its acceptance criteria, evidence, tests, timestamps, and review decision are documented.

All material work must be recorded in `BASEBALL_PROGRESS.md` or a related MDU with an exact timestamp. No work may be claimed as verified without runtime or source evidence.

## 1. Objective

Build a closed, reproducible, auditable baseball betting research and decision system that tests whether a measurable edge exists after vig, uncertainty, timing, market rules, slippage, and execution constraints.

The system must fail closed on unknown, missing, contradictory, post-kickoff, or unverifiable information. It must never invent teams, markets, odds, timestamps, statistics, results, or source evidence.

## 2. Hard boundaries

- All new production work belongs in `quantbet-baseball`.
- `h2h` is read-only legacy reference material and must not be modified.
- No live betting, automated staking, or profitability claim before chronological out-of-sample validation.
- Every market observation, prediction, pick, result, and material document must be traceable to evidence and timestamps.
- Player props are permanently out of scope.

## 3. Scope

### V1 — in scope

1. Full-game moneyline: home/away winner.
2. Full-game totals with an explicit line, beginning only with lines actually present and sufficiently covered in the data, such as 8.5 and 9.5.
3. Timestamped market observations.
4. Immutable pick events.
5. Opening/decision/closing price timeline research.
6. Settlement and post-game evaluation.
7. Chronological backtesting, calibration, CLV, and timing analysis.

### Postponed

- Run line.
- First-five-innings markets.
- Team totals.
- NRFI/YRFI and inning markets.
- Alternate lines.
- Futures.
- Parlays and same-game parlays.
- Live betting.
- Automated staking.

### Explicitly excluded — permanent project boundary

- **Player props.** This project will not research, model, implement, backtest, or deploy player-prop markets.

No excluded market may reappear in the curriculum, roadmap, implementation backlog, or future-phase scope without an explicit scope revision decision.

## 4. Phase execution order

### Phase 1 — Audit and specification

**Status:** PARTIALLY COMPLETE; audit baseline created.

Required outputs:

- repository audit;
- knowledge ledger with source, retrieval timestamp, classification, limitations, and implementation consequence;
- canonical V1 market and settlement specification;
- explicit exclusions and postponed-market register;
- separation of baseball-specific requirements from inherited/football-derived ideas.

Acceptance gate: all active documents agree on scope and the next implementation package is explicit.

### Phase 2 — Evidence and odds-timeline foundation

**Status:** CONTRACTS AND IN-MEMORY BOUNDARY IMPLEMENTED; durable persistence pending.

Implement and test:

- canonical game, market, selection, line, bookmaker, and observation identities;
- observed time, provider event time, retrieval time, ingestion time, kickoff time, decision time, and closing-observation time semantics;
- immutable raw payload references and checksums;
- duplicate and conflict handling;
- stale, suspended, incomplete, post-kickoff, and contradictory observation rules;
- opening, decision-time, subsequent, and closing observation linkage;
- immutable pick-event records containing exact price, market snapshot, model version, feature snapshot, probability, fair price, edge, EV, uncertainty, and reason;
- database-neutral repository boundary;
- PostgreSQL-backed transactional persistence;
- deterministic reads, migrations, and conflict-safe append semantics.

Acceptance gate: a historical market can be replayed from raw evidence into a decision-time pick and later closing/settlement evaluation without hidden data.

### Phase 3 — Reliable baseball data contracts

Define and validate source-backed contracts for schedules, game status, teams, probable/starting pitchers, lineups, availability, team performance, bullpen state, park factors, weather/roof, rest/travel/doubleheaders, injuries/roster changes, results, and official settlement.

Raw provider responses remain immutable. Normalized records preserve source lineage, schema version, and timestamps.

### Phase 4 — Baselines and market mathematics

Only after evidence contracts are stable:

- market-implied and de-vigged probabilities;
- Elo-style team baseline;
- pitcher/environment-adjusted run expectations;
- justified Poisson/Skellam-style baselines;
- calibrated models where data supports them;
- full-game moneyline first;
- full-game totals as distributions of total runs, never binary heuristics.

### Phase 5 — Backtesting and timing research

Use chronological train/validation/holdout splits. Measure log loss, Brier score, calibration, ROI, yield, drawdown, turnover, coverage, CLV, price movement, time-to-start, stale-odds sensitivity, slippage, rejected signals, and abstentions.

Reject any result contaminated by post-kickoff data, future lineups, future odds, leakage, or unobservable prices.

### Phase 6 — Closed replayable pipeline

`providers → immutable raw evidence → validation/normalization → canonical storage → timestamped feature snapshots → versioned models → probabilities/fair prices → market comparison → immutable pick event → odds timeline → settlement → evaluation/reporting`

Every stage must be replayable from stored evidence.

### Phase 7 — Railway operations and data lifecycle

Railway is the intended operational platform. PostgreSQL is the transactional datastore; SQLite is not part of the intended production architecture.

Implement only after contracts are credible:

- Railway service layout;
- PostgreSQL migrations and idempotency;
- ingestion/evaluation workers;
- retries, rate limits, freshness checks, health checks, and audit logs;
- automated backups and restore tests;
- archive exports with manifests and checksums;
- hot/warm/cold retention classes;
- reference-aware archival and deletion;
- rollback procedures.

Long-term cold archives may be exported to external offline storage. No data may be deleted merely because it is old; export verification and restore procedures are prerequisites.

### Phase 8 — Paper mode and launch gate

Require reproducibility, data completeness, calibration, stable operations, realistic timing behavior, untouched chronological holdout performance, and tested restore/redeploy/rollback before any limited production consideration.

## 5. Current decision

**STOP model expansion. GO on evidence architecture.**

The next concrete work package is the database-neutral repository contract followed by PostgreSQL schema, migrations, and transactional append-only persistence. Do not build the full Railway deployment yet.

## 6. Documentation protocol

Every new or modified MDU must include:

- `Created at`;
- `Last updated`;
- revision;
- status;
- relevant commit/test/source references.

Every progress entry must include an exact timestamp. Unknown source time must be recorded as unknown, not guessed.

## 7. Related MDUs

- `docs/BASEBALL_REPOSITORY_AUDIT.md` — repository findings, component status, limitations, and execution order.
- `docs/BASEBALL_DATA_LIFECYCLE_AND_RAILWAY.md` — Railway-first infrastructure, retention, backup, and archival baseline.
- `BASEBALL_PROGRESS.md` — chronological material-change log.

## 8. Completion rule

The project advances only through large, reviewable work packages. No isolated model feature should be added while the evidence, timeline, settlement, and replay foundations remain incomplete.
