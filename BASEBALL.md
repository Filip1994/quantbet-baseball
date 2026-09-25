# QuantBet Baseball v1

Standalone Baseball data, modelling, decision and paper-evaluation engine.

## Current production architecture

- **Runtime:** Railway.
- **Transactional memory:** Railway PostgreSQL.
- **Raw provider evidence:** Railway object storage.
- **Source control / CI:** GitHub.
- **Provider:** API-Sports Baseball.
- **Runtime clock:** Railway cron every 15 minutes.
- **Start command:** `PYTHONPATH=src python -m quantbot.baseball.worker`.
- **Safety:** `PAPER_MODE=true`.
- **Current production collection state:** intentionally disabled behind `BASEBALL_ENABLE_COLLECTION`.

The live runtime currently proves deployment/storage readiness. It does not yet prove a complete betting lifecycle.

## Canonical operating pattern

Baseball follows QuantBet's production lifecycle pattern:

```text
discover
→ observe
→ model
→ evaluate
→ verify final quote
→ register immutable pick
→ monitor
→ close odds
→ acquire result
→ settle
→ calculate CLV
→ evaluate
```

Football-specific model mathematics are not reused.

## Current implemented foundation

Implemented:

- bounded API client with retry/budget controls;
- raw payload archiving;
- strict pregame moneyline canonicalization;
- deterministic immutable observation identities;
- PostgreSQL migration runner;
- PostgreSQL evidence repository;
- Railway worker and advisory lock;
- moneyline market/de-vig primitives;
- Poisson moneyline baseline primitive;
- value/EV/edge primitives;
- fail-closed decision/signal primitives;
- tests around the evidence and model primitives.

Not yet closed in production:

- fixture/status persistence;
- durable prediction/evaluation events;
- mandatory final quote verification;
- registered-pick monitoring;
- closing finalization;
- results/finality;
- settlement;
- realized CLV;
- DB-backed bulletin/dashboard;
- launch-grade walk-forward validation.

## API budget policy

The subscription ceiling is 7,500 requests/day.

The current Railway design uses a 15-minute clock and a bounded per-run request budget. Collection must remain disabled until runtime telemetry and the downstream closed loop are ready, because enabling a near-ceiling schedule merely to accumulate unused evidence is wasteful.

The exact safe cadence must include retry consumption and active-pick priority.

## Market scope

### V1

- full-game moneyline;
- full-game totals with explicit line identity and sufficient real coverage.

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

## Model direction

The Baseball model is its own probability system.

Candidate inputs include:

- starting pitcher quality/handedness/workload;
- bullpen state;
- expected/confirmed lineups;
- offense/defense;
- split information;
- park;
- weather/roof;
- rest/travel/doubleheaders;
- market state.

Every production feature must be point-in-time and replayable. Model complexity is added only when chronological out-of-sample evidence shows improvement.

## Immediate target

The next completion target is **Moneyline Closed Loop v1**:

```text
fixture evidence
→ moneyline quote evidence
→ versioned probability
→ value evaluation
→ final quote verification
→ immutable paper pick
→ monitoring
→ closing
→ result
→ settlement
→ realized CLV
→ evaluation
```

See `docs/BASEBALL_COMPLETION_AUDIT_2026-09-25.md` for the canonical audit and `docs/BASEBALL_MASTER_PLAN.md` for execution gates.
