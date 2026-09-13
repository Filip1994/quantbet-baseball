# QuantBet Baseball — Progress Report

**Repository:** `Filip1994/quantbet-baseball`  
**Report date:** 2026-09-13  
**Current operating mode:** Observe-first / paper mode  
**Production betting:** Disabled

## 1. Executive summary

QuantBet Baseball has progressed from a market-observation collector into a structured, auditable baseball market-intelligence pipeline with the first offline training-data and baseline-evaluation layer.

The system can now:

- collect scheduled baseball games and bookmaker odds snapshots;
- preserve raw API responses and canonical market observations;
- track market and game lifecycle information;
- generate market-intelligence summaries;
- produce paper-only signals;
- normalize completed game results;
- construct leakage-safe pregame moneyline training rows;
- evaluate a descriptive raw-implied-probability baseline;
- validate the training layer through automated tests and GitHub Actions.

**Important:** No production-grade predictive model has been trained or validated yet. The current system is a data and evaluation foundation, not a live betting model.

## 2. What has been built from the beginning

### 2.1 Observe-first architecture

The project was designed around an observe-first principle:

1. collect market data;
2. preserve the original evidence;
3. normalize it into canonical observations;
4. inspect market structure and data quality;
5. generate paper-only signals;
6. collect outcomes;
7. build point-in-time training data;
8. evaluate models before enabling any real-money workflow.

This intentionally avoids premature automation of real-money decisions.

### 2.2 Baseball data collection

The collector was implemented to retrieve baseball games for the current and following day and then request odds for selected games within a controlled API budget.

The collector writes:

- daily snapshot JSONL files under `data/baseball/snapshots/`;
- canonical observations to `data/baseball/market_observations.jsonl`;
- raw API envelopes under `data/baseball/raw_api/`.

The collector supports a bounded odds-request budget and is used by the scheduled baseball workflow.

### 2.3 Scheduled workflow

The GitHub Actions workflow runs on a 15-minute schedule using the `Europe/Belgrade` timezone.

The workflow currently performs the following sequence:

1. collect baseball snapshots;
2. update market intelligence;
3. generate paper signals;
4. run audit/dashboard steps;
5. commit generated baseball data when changes exist.

The workflow remains explicitly paper-only. The existing collection workflow was not replaced by the training work.

### 2.4 Market intelligence

The intelligence layer reads canonical observations and produces `market_intelligence.json`.

It currently focuses on descriptive market structure rather than claiming predictive edge. It excludes player-prop markets from the relevant market-intelligence path and reports model readiness as learning-only.

Current readiness semantics include:

- `LEARNING_ONLY` status;
- zero validated predictions;
- real-money execution disabled.

### 2.5 Paper signals and lifecycle

The project uses an explicit lifecycle model:

`discovered → observing → modelled → eligible → signal → pick → closing → settled → evaluated`

This provides a basis for distinguishing raw observations, candidate signals, selected paper picks, settlement, and later evaluation.

### 2.6 Dashboard and audit contracts

The repository includes a dashboard contract at `data/baseball/dashboard.json` and audit-oriented outputs intended to make the system inspectable rather than opaque.

The dashboard and audit layers are evidence/reporting surfaces; they are not proof that a betting strategy is profitable.

## 3. Data collected so far

At the last recorded inspection, the project had approximately:

- **965 snapshot rows**;
- **157 unique games**;
- **10 leagues**;
- **13 bookmakers**;
- **46 markets**;
- **82,572 canonical observations**;
- **0 recorded API errors** in that inspection.

These figures describe collected market evidence at that point in time and will continue to change as the scheduled collector runs.

## 4. Training-data layer added

The first training-data implementation was deliberately kept small and offline. It does not introduce a database, ORM, feature store, ML framework, or new service.

### 4.1 Results normalization

`src/quantbot/baseball/results.py` now normalizes completed-game results into JSONL records containing fields such as:

- game ID;
- game date;
- home and away teams;
- home and away scores;
- status and long status;
- capture timestamp;
- source metadata.

The corresponding CLI is available through `scripts/baseball_results.py`.

### 4.2 Leakage-safe moneyline dataset

`src/quantbot/baseball/training_dataset.py` builds training rows from canonical observations and normalized results.

The current dataset builder:

- keeps only game-level moneyline / match-winner style markets;
- excludes run line, spread, total, inning, player, strikeout, hits, and other non-target markets;
- requires a valid game/event ID;
- requires valid decimal odds greater than 1.0;
- resolves the selected side against the home or away team;
- requires both capture time and kickoff time;
- excludes observations captured at or after kickoff to prevent outcome/timing leakage;
- joins observations to completed results;
- excludes tied or unresolved outcomes;
- derives the target from the winning side;
- calculates raw implied probability as `1 / odds`;
- retains source observation IDs for auditability.

The output is sorted deterministically by capture time, game ID, and selection.

The corresponding CLI is available through `scripts/baseball_training_dataset.py`.

### 4.3 Baseline evaluator

`src/quantbot/baseball/baseline.py` evaluates the raw implied probability as a descriptive baseline.

It currently reports:

- number of rows;
- number of games;
- Brier score;
- log loss;
- accuracy;
- baseline name and warning metadata.

The evaluator explicitly states that this is a **descriptive baseline and not a profitability claim**.

The corresponding CLI is available through `scripts/baseball_baseline.py`.

## 5. Tests and CI

Focused tests were added for:

- target construction and implied probability;
- exclusion of post-kickoff observations;
- exclusion of non-moneyline markets;
- handling of unknown selections;
- exclusion of tied results.

A dedicated GitHub Actions workflow was added for the training layer. It performs:

- Python setup;
- dependency installation;
- compilation checks;
- Ruff formatting/lint validation;
- test discovery and execution.

The latest recorded training workflow run completed successfully after fixing import ordering and lint issues.

## 6. What the system has learned so far

The correct interpretation is that the system has **accumulated and organized evidence**, not that a predictive ML model has already learned a reliable betting strategy.

### Evidence currently available

The collected data provides an initial historical market record containing variation across:

- games and dates;
- leagues;
- bookmakers;
- market types;
- selections;
- prices/odds;
- observation timestamps.

This is enough to begin studying market behavior, price movement, bookmaker disagreement, and the relationship between pregame prices and final outcomes.

### What has not yet been learned or proven

The project has not yet established:

- a validated baseball win-probability model;
- calibrated probabilities;
- a stable edge over bookmaker prices;
- positive expected value after vig and realistic costs;
- closing-line value performance;
- walk-forward out-of-sample performance;
- league-specific or team-specific predictive reliability;
- robustness across seasons or changing market conditions;
- profitability under realistic staking and execution assumptions.

There are currently **zero validated production predictions**.

## 7. Current limitations

1. The training dataset is still an initial moneyline-only foundation.
2. Feature engineering is not yet implemented as a point-in-time feature store or reproducible feature pipeline.
3. The current baseline uses raw implied probability and does not remove bookmaker margin.
4. No calibration layer has been implemented.
5. No walk-forward validation protocol has been implemented.
6. No closing-line-value analysis has been implemented.
7. Data coverage must continue to grow before strong conclusions can be drawn.
8. The scheduled collector and generated data require ongoing quality monitoring.
9. Paper mode remains enabled and real-money execution remains disabled.

## 8. Recommended next development sequence

### Phase 1 — Data quality and coverage

- continue collecting snapshots and results;
- add explicit data-quality reports;
- verify game IDs and team-name normalization;
- detect duplicate observations;
- measure timestamp completeness;
- quantify bookmaker and league coverage over time.

### Phase 2 — Point-in-time features

- opening and latest pregame price;
- price movement and market consensus;
- bookmaker dispersion;
- time-to-kickoff buckets;
- league and team historical features;
- starting-pitcher and lineup features when reliable data is available;
- rest, travel, and schedule context;
- weather and park factors where appropriate.

Every feature must be computed only from information available before the prediction timestamp.

### Phase 3 — Baselines and validation

- de-vig market probabilities;
- always-home / always-away and simple frequency baselines;
- logistic regression or another transparent first model;
- calibration curves and reliability diagrams;
- chronological train/validation/test splits;
- walk-forward evaluation;
- Brier score, log loss, calibration error, accuracy, and CLV.

### Phase 4 — Paper decision layer

- define minimum sample and confidence requirements;
- compare model probability with de-vig market probability;
- account for uncertainty and vig;
- log every eligible paper signal;
- evaluate realized paper performance without changing real-money status.

### Phase 5 — Governance before any live use

- independent validation;
- explicit risk limits;
- reproducible backtests;
- monitoring and rollback procedures;
- documented approval criteria;
- continued paper-mode evidence.

## 9. Current status

| Area | Status |
|---|---|
| Baseball odds collection | Implemented |
| Raw evidence preservation | Implemented |
| Canonical market observations | Implemented |
| Market intelligence | Implemented, descriptive |
| Paper signals | Implemented |
| Results normalization | Implemented |
| Leakage-safe moneyline dataset | Implemented, initial version |
| Raw implied-probability baseline | Implemented |
| Automated tests and CI | Passing |
| Calibrated predictive model | Not implemented |
| Walk-forward validation | Not implemented |
| CLV evaluation | Not implemented |
| Validated predictions | 0 |
| Real-money betting | Disabled |

## 10. Milestone recorded in this report

The first training-data and baseline-evaluation layer was merged into `main` through **PR #1**:

- PR: `Add lean baseball results, training dataset, and baseline evaluation`
- Merge commit: `36b147155c65e68190281166eb77b8645a81ad07`

This is a foundational milestone: the project now has a reproducible path from observed pregame markets to normalized outcomes, leakage-safe training rows, and an initial evaluation baseline.
