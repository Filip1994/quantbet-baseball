# QuantBet Baseball — Master Plan, Audit Baseline and Execution Layout

**Repository:** `Filip1994/quantbet-baseball`  
**Legacy reference:** `Filip1994/h2h` — read-only reference only  
**Document status:** Revised master plan after scope and learning audit  
**Last updated:** 2026-09-15 00:35 Europe/Belgrade (UTC+02:00)  
**Revision:** 2.0

## 0. Executive finding

The previously defined first phase was **not completed in a verifiable sense**.

A model being allowed to collect information or “learn” does not, by itself, establish that it learned anything useful. We currently do not have an auditable learning report containing:

- sources consulted;
- facts and concepts extracted;
- market definitions learned;
- assumptions accepted or rejected;
- source quality and conflicts;
- implemented changes attributable to research;
- tests proving the changes;
- evidence that the resulting knowledge improves prediction or betting decisions.

Therefore, the project must treat the earlier research period as **unverified exploratory activity**, not as a completed Phase 1. The next step is a formal audit and reconstruction of the knowledge base and system specification.

## 1. Objective

Build a closed, reproducible, auditable baseball betting research and decision system that can determine whether a measurable betting edge exists. The goal is not merely to predict winners or maximize hit rate. The goal is to estimate probabilities accurately enough to compare them with timestamped market prices after accounting for vig, uncertainty, timing, market rules, and execution friction.

The system must never invent teams, markets, odds, timestamps, statistics, results, or source evidence. Unknown or contradictory information must cause a controlled abstention or an explicit data-quality failure.

## 2. Scope boundary

- New production work belongs only in `quantbet-baseball`.
- `h2h` remains read-only legacy reference material.
- No live betting, automated staking, or production claims before chronological out-of-sample validation.
- Every material artifact must contain a date and time.
- Every prediction and market observation must be traceable to source evidence and a data snapshot.

## 3. Phase 1 — Baseball education, market specification and research audit

### Status: REOPENED — not yet verifiably complete

This phase has two deliverables:

1. **Knowledge audit:** establish what was actually learned from the prior research period.
2. **System specification:** convert verified knowledge into implementable, testable requirements.

The audit must classify every prior conclusion as:

- verified fact;
- source-dependent fact;
- modeling assumption;
- unresolved question;
- rejected or obsolete idea;
- implemented requirement;
- postponed feature.

The output must include source URLs or provider identifiers, retrieval timestamps, notes on conflicts, and links to the code or documentation affected. “The model knows this” is not an acceptable evidence standard.

### Required market curriculum

The system must explicitly distinguish market families and settlement rules:

1. Full-game moneyline — home/away winner.
2. Full-game run line — usually -1.5/+1.5; requires run-difference modeling.
3. Full-game total — Over/Under a specific line such as 8.5 or 9.5; each line is a separate market.
4. Team totals — one team’s runs over/under a specified line.
5. First-five-innings markets — F5 moneyline, F5 run line, F5 total; separate from full-game markets.
6. Player props — pitcher strikeouts/outs and batter outcomes; postponed until data and settlement quality are sufficient.
7. NRFI/YRFI, inning markets, alternate lines, futures, parlays, same-game parlays, and live betting — explicitly postponed.

No market may be implemented without a precise market identity, line, settlement rule, timestamp semantics, and historical odds availability.

## 4. Revised execution phases

### Phase 1 — Audit and specification

- Audit the existing repository, prior documents, commits, and implemented modules.
- Produce a verified baseball knowledge ledger.
- Define V1 markets, settlement rules, data requirements, and exclusions.
- Separate inherited ideas from `h2h`, football-derived patterns, and genuinely baseball-specific design.
- Approve the end-to-end data and decision flow before adding more modeling code.

### Phase 2 — Odds and market-timeline foundation

This is a first-class requirement, not an optional enhancement.

For every market observation, store at minimum:

- game identifier;
- market family;
- selection;
- line, where applicable;
- bookmaker/provider;
- decimal odds and raw quoted price;
- observed timestamp;
- retrieval timestamp;
- source payload/checksum;
- market status and suspension state where available.

For every candidate pick, store a separate immutable **pick event**:

- selection and exact market/line;
- odds available at decision time;
- decision timestamp;
- model version;
- feature/data snapshot timestamp;
- market snapshot identifier;
- fair probability and fair odds;
- edge, EV, uncertainty, and decision reason;
- later price observations and closing price when available.

The system must support research into opening price, price at model decision, subsequent movement, closing line, stale odds, slippage, and the relationship between decision timing and realized value.

### Phase 3 — Reliable baseball data

Collect only timestamp-valid information on:

- schedules and game status;
- teams and identities;
- starting/probable pitchers;
- lineups and player availability;
- team and player performance;
- bullpen quality and availability;
- park and venue factors;
- weather and roof status;
- rest, travel, doubleheaders, injuries, and roster changes;
- results and official settlement data.

Raw provider responses are immutable evidence. Normalized data must preserve source lineage and schema version.

### Phase 4 — Baselines and market-specific mathematics

Build simple, testable baselines first:

- market-implied and de-vigged probabilities;
- Elo-style team strength;
- pitcher- and environment-adjusted run expectations;
- Poisson/Skellam-style run models where assumptions are justified;
- calibrated classifiers where appropriate.

V1 modeling priority:

- full-game moneyline;
- full-game totals for explicitly observed lines such as 8.5 and 9.5.

Run line and F5 markets follow only after their data, modeling, and settlement requirements are specified. Totals must model the distribution of total runs, not use a binary heuristic.

### Phase 5 — Backtesting and timing research

Use strictly chronological train/validation/holdout splits. Evaluate:

- log loss and Brier score;
- calibration and reliability by probability bucket;
- ROI, yield, drawdown, turnover, and coverage;
- performance by market, line, bookmaker, odds range, and time-to-start;
- closing-line value and price movement;
- stale-odds and missing-data sensitivity;
- selection bias, rejected signals, and abstentions;
- slippage and realistic execution assumptions.

A profitable backtest is not accepted if it depends on post-kickoff data, future lineups, future odds, leakage, or unobservable prices.

### Phase 6 — Closed end-to-end pipeline

Providers → immutable raw evidence → validation/normalization → canonical database → timestamped feature snapshots → versioned models → probabilities/fair prices → market comparison → decision/pick event → later odds timeline → settlement → evaluation/reporting.

Every stage must be replayable from stored evidence.

### Phase 7 — Railway deployment and operational controls

Railway PostgreSQL is the operational source of truth. Persistent storage is used for raw archives, Parquet/DuckDB research artifacts, exports, and backups where appropriate.

Add idempotency, retries, rate-limit handling, freshness checks, health checks, audit logs, backup/restore procedures, and safe migration practices. No destructive cutover is allowed without verified rollback capability.

### Phase 8 — Paper mode and launch gate

Run in shadow/paper mode first. Require documented evidence for:

- reproducibility;
- data freshness and completeness;
- calibrated probabilities;
- stable operations;
- realistic market-timing behavior;
- acceptable performance on an untouched chronological holdout;
- tested restore, redeploy, and rollback procedures.

Only then may limited production output be considered.

## 5. V1 decision

The initial V1 will support:

- full-game moneyline;
- full-game totals with an explicit total line, beginning with commonly observed lines such as 8.5 and 9.5;
- timestamped odds observations and immutable pick events;
- settlement and post-game evaluation.

The following are postponed: run line, F5 markets, team totals, player props, NRFI/YRFI, alternate lines, futures, parlays, same-game parlays, live betting, and automated staking.

This is a sequencing decision, not a claim that those markets are unimportant.

## 6. Definition of “learned”

A baseball concept is considered learned by the project only when it has:

1. a written definition;
2. a source and retrieval timestamp;
3. explicit assumptions and limitations;
4. a mapped data contract or implementation requirement;
5. a test, fixture, or validation method where applicable;
6. a decision on whether it belongs in V1, later, or nowhere.

## 7. Documentation and timestamp protocol

Every new or modified document must include:

- `Created at: YYYY-MM-DD HH:MM TZ`;
- `Last updated: YYYY-MM-DD HH:MM TZ`;
- revision number;
- status;
- links to relevant commits, tests, source evidence, and decision records.

Every progress entry must include an exact timestamp. If a source has no reliable publication or retrieval time, that uncertainty must be recorded rather than guessed.

## 8. Completion rule

A phase is not complete because code exists or because information was collected. It is complete only when its documented acceptance criteria, evidence, tests, and review decision are present.

**Immediate next action:** perform the formal repository and research audit, then create the knowledge ledger, market specification, and odds-timeline design before further expanding model functionality.
