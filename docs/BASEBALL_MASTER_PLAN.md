# QuantBet Baseball — Master Plan to Launch

**Repository:** `Filip1994/quantbet-baseball`  
**Legacy reference:** `Filip1994/h2h`  
**Status:** Planning and audit baseline  
**Last updated:** 2026-09-14

## 1. Objective

Build a reliable, reproducible baseball betting research and decision system. The system must produce auditable pre-game probabilities, fair prices, edge estimates, candidate bets, and post-game evaluation without data leakage.

The baseball repository is the only target repository for new production work. The `h2h` repository is read-only legacy reference material until a component is explicitly approved for porting.

## 2. Non-negotiable principles

- No post-kickoff information may enter a pre-game prediction.
- Raw provider responses are immutable evidence.
- Every prediction must have a model version, data snapshot, feature timestamp, and source lineage.
- Unknown teams, markets, selections, odds, or timestamps fail closed.
- No live betting or automated staking before out-of-sample validation and launch approval.
- All migrations are reversible and verified before cutover.
- Documentation is part of the deliverable; every meaningful change updates a progress log.

## 3. Workstreams

### W0 — Repository and legacy audit
- Inventory the baseball repository, workflows, data, tests, configuration, and deployment assumptions.
- Inventory `h2h` modules and classify them as: reusable, adaptable, unsafe, or obsolete.
- Produce a porting decision record for each candidate component.

### W1 — Test foundation
- Establish deterministic unit, integration, contract, regression, and leakage tests.
- Add CI gates for formatting, type checks where applicable, tests, and data-contract validation.
- Add fixtures for baseball games, odds, markets, outcomes, and timestamps.

### W2 — Baseball domain model
- Define canonical game, team, player, lineup, pitcher, venue, weather, odds, market, prediction, bet, and settlement schemas.
- Define identity resolution and team aliases.
- Define supported markets; initially prioritize moneyline and explicitly exclude unsupported markets.

### W3 — Data ingestion and evidence layer
- Collect schedules, game metadata, results, team/player statistics, probable pitchers, lineups, weather, and odds.
- Store raw payloads immutably with retrieval timestamp, provider, endpoint, checksum, and schema version.
- Build normalized tables/data files from raw evidence.

### W4 — Baseball mathematics and modeling
- Establish baseline models before advanced models.
- Baselines: market-implied probability, Elo-style team strength, pitcher-adjusted run environment, and a Poisson/Skellam run model where appropriate.
- Add calibration, shrinkage, uncertainty, and model versioning.
- Produce probabilities for supported outcomes, then convert to fair odds and edge.

### W5 — Backtesting and validation
- Use strictly chronological splits.
- Separate training, validation, and final holdout periods.
- Measure log loss, Brier score, calibration, ROI, yield, drawdown, turnover, coverage, and closing-line performance where available.
- Include selection bias, missing-data, stale-odds, and postponed-game tests.

### W6 — Railway deployment and migration
- Railway PostgreSQL is the operational source of truth.
- Railway persistent volume stores raw archives, DuckDB/Parquet artifacts, exports, and backups where appropriate.
- Deploy separate ingestion, modeling, API/dashboard, and scheduled-worker responsibilities only when justified by load.
- Perform dual-write/backfill/verification before cutover.

### W7 — Production controls
- Add health checks, freshness checks, data-quality checks, idempotency, retries, rate-limit handling, alerting, and audit logs.
- Add manual approval for production model promotion.
- Add rollback runbooks and backup restore drills.

### W8 — Launch
- Freeze scope.
- Run launch checklist and final holdout evaluation.
- Start in shadow mode.
- Compare predictions and operational metrics against acceptance thresholds.
- Enable limited production output only after explicit approval.

## 4. Proposed target architecture

```text
Providers/APIs
    -> immutable raw evidence on Railway Volume
    -> ingestion/normalization workers
    -> Railway PostgreSQL canonical data
    -> feature snapshots / Parquet or DuckDB research artifacts
    -> versioned baseball models
    -> predictions + fair prices + edge
    -> API/dashboard/reporting
    -> settlement and evaluation
```

GitHub is the code and documentation source of truth. Railway is the runtime and operational data platform. Secrets live only in Railway variables or an approved secret manager; never in Git.

## 5. Baseball mathematical scope

Initial supported outcome: **two-way pre-game moneyline**.

For each game:

- Estimate expected runs for home and away teams.
- Convert expected runs to win probabilities using a suitable run-scoring model or calibrated classifier.
- Adjust for starting pitchers, bullpen availability, park, weather, platoon effects, rest, travel, injuries/lineups, and schedule context only when timestamp-valid.
- Compare model probability `p_model` with de-vigged market probability `p_market`.
- Compute edge as `p_model - p_market` and expected value using decimal odds.
- Attach uncertainty and minimum-data requirements; abstain when evidence is insufficient.

Advanced markets (run line, totals, props, same-game parlays) are out of scope until moneyline data quality and calibration are proven.

## 6. Railway migration sequence

1. Inventory current Railway project, services, variables, volumes, domains, and deployment source.
2. Create a non-destructive staging environment.
3. Provision/verify PostgreSQL and persistent volume.
4. Define schema migrations and backup policy.
5. Add idempotent ingestion and raw-evidence storage.
6. Backfill a bounded historical slice.
7. Compare source and target counts, checksums, timestamps, and key aggregates.
8. Run application in read-only verification mode.
9. Enable dual-write where needed.
10. Observe for a defined period.
11. Cut over reads and scheduled jobs.
12. Keep rollback path and old artifacts until acceptance is signed off.

No destructive deletion, force push, or production cutover is permitted as part of preparation.

## 7. Launch acceptance criteria

- CI is green on the default branch.
- All critical domain and leakage tests pass.
- No unresolved critical data-contract violations.
- Raw evidence is recoverable from backup.
- Predictions are reproducible from a pinned data/model snapshot.
- Chronological holdout results are documented.
- Calibration is acceptable for the intended use.
- Shadow-mode operations are stable.
- Railway restart, redeploy, and restore procedures are tested.
- Rollback owner, trigger, and exact steps are documented.

## 8. Documentation protocol

Every workstream has:

- one high-level progress entry in `BASEBALL_PROGRESS.md`;
- one detailed execution document under `docs/steps/`;
- a dated decision record for architecture or modeling changes;
- links to commits, tests, migrations, and evidence artifacts.

A task is not complete until implementation, tests, evidence, and documentation are all updated.
