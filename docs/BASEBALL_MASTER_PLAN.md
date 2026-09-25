# QuantBet Baseball — Master Plan and Execution Layout

**Repository:** `Filip1994/quantbet-baseball`  
**Created at:** 2026-09-15 Europe/Belgrade  
**Last updated:** 2026-09-25 Europe/Belgrade  
**Revision:** 4.0  
**Status:** ACTIVE COMPLETION PLAN — QuantBet lifecycle parity, Baseball-specific model

## 0. Canonical rule

The project advances by **closed vertical slices**.

A component is not complete because code exists. A slice is complete only when its evidence, persistence, replay behavior, tests, runtime behavior, and acceptance gate are verified.

No profitability claim is permitted before chronological out-of-sample validation.

## 1. Objective

Build a closed, reproducible and auditable Baseball value-betting engine that can:

1. discover games;
2. preserve exact pregame market evidence;
3. calculate a point-in-time Baseball probability;
4. compare fair probability/price with executable market price;
5. verify the exact quote again immediately before registration;
6. register an immutable paper pick;
7. monitor that pick until first pitch;
8. finalize a valid closing quote;
9. acquire and stabilize the authoritative result;
10. settle the pick;
11. calculate realized CLV;
12. evaluate performance and calibration;
13. reproduce every decision from stored evidence.

Railway is the production runtime/control plane. PostgreSQL is canonical transactional memory. Railway object storage preserves raw provider evidence. GitHub is source control and CI.

## 2. Scope

### V1

- full-game moneyline;
- full-game totals with explicit line identity and sufficient historical coverage;
- immutable quote history;
- immutable decision/pick evidence;
- opening/pick/current/closing quote checkpoints;
- result acquisition and settlement;
- realized CLV;
- chronological backtesting, calibration and walk-forward evaluation;
- paper-only operation.

### Postponed

- run line;
- first five innings;
- team totals;
- NRFI/YRFI;
- inning markets;
- alternate lines;
- futures;
- parlays/SGPs;
- live betting;
- automated staking.

### Permanently excluded

- **player props**.

## 3. Current verified state

As of 2026-09-25:

- Railway application service exists and deploys successfully;
- production cron is configured every 15 minutes;
- PostgreSQL exists and migrations are applied;
- Railway object storage bucket exists;
- durable canonical moneyline ingestion exists;
- raw payloads are archived before canonicalization;
- `odds_observations` and `pick_events` exist;
- production `pick_events` count was observed as 0;
- collection is currently disabled via `BASEBALL_ENABLE_COLLECTION=false`;
- runtime therefore operates in `storage-ready` mode;
- totals are not yet canonically ingested;
- no closed production pick lifecycle exists yet.

The canonical detailed audit is:

- `docs/BASEBALL_COMPLETION_AUDIT_2026-09-25.md`.

## 4. Architecture rule inherited from QuantBet

Baseball inherits QuantBet's lifecycle discipline:

```text
discovery
→ immutable evidence
→ point-in-time model
→ evaluation
→ preliminary candidate
→ final quote verification
→ immutable registration
→ monitoring
→ closing
→ result finality
→ settlement
→ realized CLV
→ evaluation
```

Baseball does **not** inherit football market mathematics or football features.

## 5. Completion sequence

### Slice A — Runtime truth and fixture evidence

Implement:

- canonical fixture registry;
- append-only fixture observations;
- kickoff/status change history;
- runtime collection-cycle telemetry;
- DB freshness/coverage queries;
- controlled collector canary;
- restart/idempotency tests.

**Gate A:** one canary run proves raw archive + fixture writes + moneyline writes + telemetry with bounded API use.

Scheduled collection remains disabled until Gate A passes.

### Slice B — Moneyline decision and registration

Implement:

- point-in-time feature snapshot contract;
- versioned prediction event;
- canonical market snapshot from stored quotes;
- de-vigged market probability;
- value evaluation;
- preliminary candidate;
- mandatory final quote verification and repricing;
- immutable registered pick;
- rejection reason codes;
- end-to-end registration tests.

**Gate B:** a synthetic and a real paper fixture can deterministically move from stored evidence to either REGISTERED or an explicit fail-closed rejection.

### Slice C — Monitoring and closing

Implement:

- registered-pick monitoring states;
- API-budget priority for active picks;
- quote refresh cadence toward first pitch;
- first/pick/current/closing projections;
- immutable closing finalization;
- stale/no-valid-closing outcomes;
- restart-safe workers.

**Gate C:** registered paper picks receive deterministic closing outcomes without mutation of entry evidence.

### Slice D — Result, settlement and CLV

Implement:

- Baseball result observations;
- result finality/stability policy;
- moneyline settlement rules;
- append-only settlement events;
- paper P&L;
- realized CLV facts;
- correction handling.

**Gate D:** every registered moneyline pick reaches SETTLED and a deterministic CLV availability state.

### Slice E — Operational product

Implement:

- DB-backed Daily Bulletin;
- operational API/dashboard projection;
- health/freshness/budget metrics;
- alerts;
- replay/restore procedure;
- archive verification.

**Gate E:** dashboard and bulletin can be rebuilt from canonical storage without Git-generated operational state.

### Slice F — Research and model promotion

Implement:

- historical canonical backfill;
- point-in-time Baseball feature dataset;
- simple baselines before complex models;
- calibration;
- chronological train/validation/holdout;
- walk-forward;
- CLV analysis;
- model promotion records.

**Gate F:** a production model version is accepted only after a documented untouched holdout/walk-forward decision.

### Slice G — Totals

After the moneyline loop is fully green, repeat the decision/monitoring/settlement/validation lifecycle for full-game totals.

**Gate G:** totals have exact line identity, line-specific monitoring, settlement semantics and validation.

## 6. Model principles

Model sophistication is subordinate to evidence quality.

Start with transparent baselines and add complexity only when out-of-sample evidence justifies it.

Candidate Baseball inputs may include:

- starting pitcher quality and handedness;
- pitcher workload/rest;
- bullpen workload and availability;
- expected/confirmed lineups;
- team offensive/defensive rates;
- platoon/split information;
- park factors;
- weather/roof where reliable;
- rest/travel/doubleheader context;
- market state.

Every feature used in a decision must have a point-in-time cutoff that proves it was available before the decision.

## 7. Evaluation requirements

At minimum record:

- log loss;
- Brier score;
- calibration;
- coverage/abstention;
- ROI/yield;
- drawdown;
- realized CLV;
- time-to-first-pitch;
- stale-price sensitivity;
- performance by league/bookmaker;
- model version;
- data-quality exclusions.

Look-ahead leakage, survivorship bias and post-start observations invalidate an experiment.

## 8. Production activation gate

Do not enable the scheduled collector merely because Railway is healthy.

Before `BASEBALL_ENABLE_COLLECTION=true`:

1. Slice A is green;
2. exact API budget math including retries is verified;
3. one bounded canary succeeds;
4. DB freshness/coverage is visible;
5. raw archive writes are verified;
6. no identity conflicts occur;
7. downstream paper lifecycle is ready to consume the evidence.

Production remains `PAPER_MODE=true`.

## 9. Definition of done

The project is finished as a paper engine when:

- moneyline and approved totals traverse the full closed lifecycle;
- every registered pick is reproducible;
- final quote verification is mandatory;
- closing and settlement are immutable/restart-safe;
- realized CLV has exact provenance;
- the operational dashboard reads canonical DB truth;
- restore/replay is tested;
- chronological validation is documented;
- no excluded market has leaked back into scope.

## 10. Related documents

- `docs/BASEBALL_COMPLETION_AUDIT_2026-09-25.md` — current canonical audit.
- `docs/BASEBALL_DATA_LIFECYCLE_AND_RAILWAY.md` — persistence/retention architecture.
- `docs/BASEBALL_REPOSITORY_CONTRACT.md` — evidence repository semantics.
- `BASEBALL_PROGRESS.md` — chronological implementation log.
