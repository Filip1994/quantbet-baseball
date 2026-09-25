

## 28. Append-only evidence store boundary — 2026-09-15

Added `src/quantbot/baseball/evidence_store.py` as the first persistence boundary.

Implemented:

- append-only in-memory storage for validated odds observations and pick events;
- idempotent exact duplicate handling;
- fail-closed conflict handling by immutable observation/pick identity;
- deterministic retrieval ordering;
- batch observation append support;
- basic store statistics.

Added `tests/test_evidence_store.py` covering exact duplicates, conflicting duplicates, and deterministic ordering.

This is intentionally storage-agnostic and does not yet claim durable persistence. A database adapter will be added only after the contract and conflict semantics are stabilized.

Commits:

- `c1f5bce` — add append-only evidence store boundary;
- `88b949f` — verify append-only evidence store semantics.

Runtime tests were not independently executed in this environment.

## 29. Railway-first data lifecycle baseline — 2026-09-15

Established the architectural direction that Railway is the intended operational platform for QuantBet Baseball.

Decision:

- PostgreSQL is the intended transactional datastore;
- SQLite is not part of the intended production architecture;
- Railway hosts the operational services, workers, scheduler, and database;
- long-term historical data may be exported to a verified cold archive;
- raw payloads and detailed historical observations may eventually move from hot storage to warm/cold storage;
- pick events, settlement, CLV, model metadata, and audit lineage remain retained as the compact evidence trail.

Added:

- `docs/BASEBALL_DATA_LIFECYCLE_AND_RAILWAY.md` — target architecture, hot/warm/cold data classes, retention rules, backup requirements, scale principles, and implementation order;
- updated `docs/BASEBALL_MASTER_PLAN.md` to revision 3.1 and aligned Phase 7 with Railway-first persistence and archival.

Important constraints:

- no automatic deletion based on age alone;
- archive export requires manifest, checksums, read-back verification, and tested restore/import procedures;
- monthly cold export is not the only backup;
- storage capacity and RAM/query capacity are separate engineering concerns.

Commits:

- `94aabd2` — define Railway-first data lifecycle architecture;
- `aae3040` — align master plan with Railway-first persistence.

Documentation-only change. Runtime tests were not executed.

## 30. Storage-neutral repository contract — 2026-09-15

Added `src/quantbot/baseball/evidence_repository.py` defining the minimal repository protocol for canonical odds observations and immutable pick events.

Added `docs/BASEBALL_REPOSITORY_CONTRACT.md` documenting adapter obligations:

- immutable identities;
- idempotent exact duplicates;
- fail-closed conflicts;
- no silent overwrite;
- canonical equality;
- deterministic reads;
- schema visibility;
- transaction boundaries;
- replay safety;
- auditability.

The contract remains independent of Railway and PostgreSQL, while PostgreSQL on Railway is the intended production implementation. Settlement, archival jobs, retention deletion, and provider ingestion remain separate future slices.

Commits:

- `5d0564c` — define storage-neutral evidence repository contract;
- `ac54e80` — specify evidence repository contract and adapter obligations.

Runtime tests were not executed.

## 31. PostgreSQL evidence schema foundation — 2026-09-15

Added:

- `migrations/001_create_evidence_tables.sql`;
- `docs/BASEBALL_POSTGRES_SCHEMA.md`.

The migration defines the initial durable relational boundary for:

- `odds_observations`;
- `pick_events`.

Included:

- immutable UUID primary keys;
- canonical JSONB record retention;
- schema-version fields;
- timestamp fields and basic temporal constraints;
- market-family and status/decision constraints;
- probability and odds validation;
- indexes for game, market, line, bookmaker, and decision-time retrieval;
- explicit PASS metric nullability rules.

The migration is not connected to Railway and has not been applied to a live PostgreSQL instance. Provider ingestion, settlement, archival jobs, retention deletion, and deployment configuration remain outside this milestone.

Commits:

- `06ca3b3` — add PostgreSQL evidence schema foundation;
- `921ad25` — document PostgreSQL evidence schema foundation.

Runtime tests and live database migration verification were not executed.

## 32. Database invariant hardening — 2026-09-15

Hardened `migrations/001_create_evidence_tables.sql` with explicit checks for:

- valid decimal odds for pick events;
- valid fair decimal odds;
- required metrics for `BET` events;
- null metrics for `PASS` events.

This prevents incomplete or semantically contradictory pick records from entering the future PostgreSQL evidence store.

Commit:

- `fb9d80f` — tighten pick event database invariants.

Runtime tests and live database migration verification were not executed.

## 33. PostgreSQL contract alignment and atomic batch boundary — 2026-09-15

Aligned the PostgreSQL schema with the canonical Python evidence contracts:

- standardized market families to `moneyline` and `total`;
- allowed `NULL` lines for moneyline records;
- required `kickoff_at` for odds observations;
- enforced pre-kickoff observation timestamps;
- aligned supported market statuses;
- added line-family consistency checks.

Updated `src/quantbot/baseball/postgres_repository.py` to:

- persist `kickoff_at`;
- use the aligned market contract;
- preserve exact canonical JSON for duplicate comparison;
- provide an atomic observation batch boundary with one final commit and rollback on failure.

Commits:

- `1e66e417` — align PostgreSQL schema with evidence contracts;
- `749ad3b2` — align PostgreSQL adapter and add atomic observation batches.

Runtime tests, PostgreSQL migration execution, and live Railway verification were not performed.

## 34. Railway runtime reconnaissance — 2026-09-15T11:36+02:00

Confirmed the Baseball Railway project and inspected its first deployment.

Railway project:

- project: `believable-contentment`;
- service: `quantbet-baseball`;
- environment: `production`.

The first deployment failed during Railpack preparation because no start command was detected. The repository contains batch-oriented scripts such as `scripts/baseball_audit.py`, but no confirmed production service entrypoint was established during this reconnaissance.

Important findings:

- `pyproject.toml` declares no runtime dependencies;
- `requirements.txt` states that the runtime uses only the Python standard library;
- the PostgreSQL adapter imports no external driver directly and expects a DB-API connection to be supplied;
- Railway has not been proven to run a worker, scheduler, ingestion process, or API polling loop;
- no Railway configuration or production variable was changed;
- the unrelated `sincere-balance` project was not used for this verification.

Open issue:

- README scope language still mentions player props as a later possibility, which conflicts with the project decision that player props are permanently `OUT OF SCOPE`. This must be corrected before treating the documentation as fully aligned.

Next step:

- perform a complete entrypoint/dependency/CI review, then introduce the smallest explicit and safe Railway start command only after the intended runtime process is confirmed.

Runtime tests, PostgreSQL migration execution, and live application startup were not performed.

## 35. Scope alignment and CI reconnaissance — 2026-09-15

Completed the next reconnaissance slice:

- enumerated the repository's `scripts/` directory;
- confirmed that the scripts are batch/research utilities, not a verified long-running production entrypoint;
- inspected the scheduled collection workflow;
- inspected the test workflow;
- confirmed that scheduled collection currently runs through GitHub Actions every 15 minutes, not through a proven Railway worker;
- confirmed that the collection workflow invokes the collector, intelligence build, signal scan, audit, and dashboard scripts;
- confirmed that the test workflow installs `requirements-dev.txt`, runs compilation, Ruff formatting/lint checks, and `pytest`;
- corrected `README.md` so the supported scope is explicitly full-game moneyline and full-game totals, while player props and other excluded market classes are explicitly out of scope.

The README correction was committed as:

- `a3ee228` — align README with permanent baseball market scope.

No Railway start command was added. No deployment configuration was changed. No runtime tests, PostgreSQL migration execution, or live Railway startup verification were performed.

Remaining decision gate:

- determine whether Railway should host a real application process at this stage or remain reserved for the future PostgreSQL/worker architecture; do not create a placeholder start command merely to satisfy Railpack.

## 36. Collection-vs-Railway boundary reconnaissance — 2026-09-15

Additional review confirmed:

- `baseball-collect.yml` is the current operational collection path;
- it runs every 15 minutes in `Europe/Belgrade` and performs collection, intelligence generation, signal scanning, audit generation, and dashboard generation;
- the workflow commits generated data back to `main`, meaning the current operational data plane is Git-based rather than PostgreSQL-backed;
- the collection workflow uses a bounded request budget and requires `API_BASEBALL_KEY`, but this was inspected statically and not executed here;
- `baseball-training.yml` is a validation workflow, not a production trainer or scheduler;
- the repository's scripts expose one-shot `main()` functions and CLI arguments, but no verified daemon, HTTP health endpoint, or persistent worker loop was found in the inspected surface;
- `pyproject.toml` has no runtime dependencies, while CI depends on `requirements-dev.txt`; the exact contents of that file and the complete dependency chain still require explicit verification before PostgreSQL integration or Railway runtime packaging.

Architectural consequence:

> The project currently has a GitHub Actions data-footprint pipeline and a partially prepared persistence layer, but not yet a deployable Railway application.

No code or Railway configuration was changed in this slice. No runtime tests, API calls, migration execution, or live deployment verification were performed.

Next gate:

- inspect `requirements.txt`, `requirements-dev.txt`, the collector/configuration modules, and the complete PostgreSQL adapter/migration together;
- then define the smallest legitimate runtime boundary rather than adding a placeholder process.

## 37. Railway as runtime and memory control plane — 2026-09-15

The project owner explicitly selected Railway as the operational execution and persistence platform.

Confirmed architectural intent:

- **GitHub** is the source-code, version-control, review, and CI system;
- **Railway** is the runtime control plane: startup, scheduled execution, workers, runtime configuration, secrets, logs, health checks, and operational orchestration;
- **Railway PostgreSQL** is the canonical persistent memory for market evidence, immutable picks, settlement, CLV, model metadata, and audit lineage;
- **GitHub Actions** may remain for CI and repository validation, but must not remain the production source of truth or primary ingestion engine;
- generated operational state should be written to PostgreSQL rather than committed back into GitHub;
- external cold archives are secondary, verified long-term storage.

Updated:

- `docs/BASEBALL_DATA_LIFECYCLE_AND_RAILWAY.md` to revision 1.1;
- added explicit runtime ownership rules and Railway acceptance criteria.

Commit:

- `75d108b` — make Railway the explicit runtime and persistence control plane.

No Railway configuration, credentials, database migration, or live deployment was changed in this slice. The next implementation step is to define and build the first legitimate Railway runtime boundary, then connect it to PostgreSQL safely.

## 38. Railway PostgreSQL runtime foundation — 2026-09-17

Implemented and deployed the first legitimate Railway production runtime boundary.

Verified implementation:

- Railway project `believable-contentment`;
- service `quantbet-baseball`;
- PostgreSQL service with persistent Railway volume;
- explicit worker entrypoint: `PYTHONPATH=src python -m quantbot.baseball.worker`;
- pre-deploy migration execution;
- `schema_migrations` tracking;
- runtime dependencies for PostgreSQL;
- safe default mode with collection disabled unless explicitly enabled.

Relevant commit:

- `c1da18f14` — add Railway PostgreSQL runtime foundation.

This supersedes milestones 34–37 where Railway was still reconnaissance/intent only.

## 39. Durable canonical Railway ingestion — 2026-09-18

Implemented the first durable Railway data path:

```text
API-Sports Baseball
→ raw immutable Railway object archive
→ strict canonical moneyline normalization
→ Railway PostgreSQL odds_observations
```

Implemented:

- remote raw-payload archiving;
- deterministic canonical observation IDs;
- strict pregame guard;
- moneyline-only canonical ingestion;
- PostgreSQL append/idempotency semantics;
- PostgreSQL advisory locking;
- bounded per-run odds selection;
- integration tests around migration/repository behavior.

Relevant commit:

- `968b1b191` — add durable canonical Baseball ingestion.

Important limitation:

- the durable production mapper currently canonicalizes **moneyline only**;
- the complete pick/monitoring/closing/settlement/CLV lifecycle is not yet connected.

## 40. Global repository cleanup / CI baseline — 2026-09-18

Repository head advanced to:

- `412e73703bc4366047ba02b64dbb3bd30c48b7a2` — make global Baseball CI green.

The commit includes formatting/lint cleanup, decision-threshold corrections, temporal test fixes, exact training-observation deduplication, and PostgreSQL integration-test scoping.

Railway deployment for this commit is currently reported `SUCCESS`.

## 41. Production runtime audit and collection gate — 2026-09-25T12:47+02:00

Performed a live GitHub + Railway audit before further model work.

Verified current Railway state:

- `quantbet-baseball` runs on a 15-minute cron;
- start command is `PYTHONPATH=src python -m quantbot.baseball.worker`;
- PostgreSQL and raw object storage exist;
- latest inspected deployment is `SUCCESS`;
- production logs repeatedly report:
  - `collection_enabled=false`;
  - `mode="storage-ready"`;
  - `status="ready"`.

Therefore:

> The scheduler is healthy, but production data collection is intentionally disabled.

A production DB inspection also confirmed:

- tables `schema_migrations`, `odds_observations`, and `pick_events` exist;
- `pick_events` count is 0 at the inspected time.

Exact `odds_observations` count/freshness was not established through the available read-only connector, so no row-count assumption is recorded.

Decision:

- do **not** enable the collector yet;
- first close the QuantBet-style moneyline lifecycle so API budget is not spent producing evidence with no downstream decision/evaluation loop.

## 42. QuantBet-parity completion audit — 2026-09-25T12:47+02:00

Created:

- `docs/BASEBALL_COMPLETION_AUDIT_2026-09-25.md`.

The audit changes the execution strategy from phase-oriented partial components to closed vertical slices.

Canonical target:

```text
fixture discovery
→ canonical quote evidence
→ point-in-time prediction
→ value evaluation
→ preliminary candidate
→ mandatory final quote verification
→ immutable registered pick
→ post-pick monitoring
→ closing finalization
→ authoritative result
→ settlement
→ realized CLV
→ performance evaluation
```

The first completion target is **Moneyline Closed Loop v1**.

QuantBet football is now the reference for lifecycle discipline only. Football-specific market/model mathematics must not be copied into Baseball.

Next implementation package:

1. canonical fixture persistence;
2. runtime-cycle telemetry and DB health/freshness visibility;
3. moneyline prediction/evaluation contracts;
4. mandatory final quote verification;
5. immutable pick registration;
6. end-to-end tests through registration.

Scheduled production collection remains disabled until the canary/observability acceptance gate is met.

## 43. Package A — canonical runtime truth and fixture evidence — 2026-09-25

Completed the first QuantBet-parity completion slice on branch `finish/quantbet-parity-20260925`.

Implemented:

- canonical stable `fixtures` identity table with API-Sports Baseball provider game/team identifiers;
- append-only `fixture_observations` preserving kickoff/status/name evidence and raw-payload provenance;
- durable `collection_cycles` for actual collector attempts;
- separate `runtime_cycles` for every Railway worker invocation, including storage-ready runs while collection is disabled;
- DB-backed `health_snapshot()` exposing fixture/quote/pick counts, bookmaker coverage, latest evidence timestamps, collection-cycle count, and Railway runtime-cycle count;
- fresh schedule retrieval with durable raw archive receipts;
- fixture persistence before odds-selection decisions;
- collection-cycle persistence around advisory-lock and collection execution paths;
- PostgreSQL integration coverage for fixture replay/idempotency, collection cycles, runtime cycles, and health projection.

Reconciled duplicate implementation work:

- retained the richer canonical fixture model in `fixture_evidence.py` with provider/team identities and the stable `fixtures` table;
- removed the temporary duplicate minimal operational fixture implementation;
- retained two telemetry layers intentionally:
  - `collection_cycles` = actual collector attempts;
  - `runtime_cycles` = every Railway cron invocation.

CI evidence:

- Railway runtime smoke: **SUCCESS**;
- global Baseball tests: **SUCCESS**;
- compile, Ruff format, Ruff lint, pytest, migrations and PostgreSQL integration are green.

Safety / production state:

- `BASEBALL_ENABLE_COLLECTION` remains disabled;
- no production API collection was enabled during this package;
- no football Railway project or football repository was modified.

Next package:

> Package B — Moneyline decision chain: point-in-time prediction evidence → value evaluation → mandatory final quote verification → immutable registered paper pick.

## 44. Package B — Moneyline decision chain and mandatory final quote verification — 2026-09-25

Completed the second QuantBet-parity vertical slice on branch `finish/moneyline-closed-loop-20260925`.

Implemented migration `004_moneyline_decision_chain.sql` and the durable lifecycle:

```text
point-in-time model prediction
→ exact bookmaker moneyline pair
→ de-vig/value evaluation
→ preliminary candidate
→ mandatory fresh exact-bookmaker quote pull
→ final repricing
→ READY / REJECTED verification
→ immutable registered paper pick
```

Implemented:

- versioned `model_predictions` with feature snapshot reference, source-data cutoff, prediction time, two-way probabilities and uncertainty;
- durable `value_evaluations` for both PRELIMINARY and FINAL stages;
- exact home/away observation provenance for every evaluation;
- de-vigged market probability, fair odds, edge and EV persistence;
- quote-age and uncertainty fail-closed gates;
- `final_quote_verifications` with REQUESTED / READY / REJECTED state;
- fresh API-Sports odds re-fetch immediately before registration;
- exact bookmaker/selection identity preservation during final verification;
- final price deterioration rejection;
- `registered_picks` with exact entry observation/odds and `paper_mode = TRUE` database constraint;
- one full-game moneyline pick per game boundary;
- restart-safe READY replay and REJECTED replay behavior;
- runtime health counts for predictions, evaluations, final verifications and registered picks.

Verification evidence:

- global Baseball compile / Ruff format / Ruff lint / pytest: **SUCCESS**;
- Railway PostgreSQL smoke: **SUCCESS**;
- happy-path PostgreSQL integration proves fresh-quote gated registration and replay;
- negative PostgreSQL integration proves final price deterioration produces REJECTED verification and no pick;
- focused Railway smoke now explicitly covers Package B source files and tests.

Safety:

- no real-money execution was added;
- no automatic staking was added;
- scheduled production collection remains disabled;
- no football Railway project or football repository was modified.

Next package:

> Package C — registered-pick monitoring, active-pick API priority, deterministic opening/pick/current/closing quote checkpoints, and immutable closing finalization.

## 45. Package C — registered-pick monitoring and immutable closing — 2026-09-25

Completed the third QuantBet-parity vertical slice on branch `finish/moneyline-monitoring-closing-20260925`.

Implemented migration `005_moneyline_monitoring_closing.sql` and the active-pick odds lifecycle:

```text
registered paper pick
→ MONITORING
→ active-pick fixture refresh
→ exact-bookmaker moneyline refresh
→ OPEN / ENTRY / CURRENT lifecycle projection
→ authoritative kickoff cutoff
→ immutable CAPTURED / STALE_QUOTE / NO_VALID_QUOTE closing fact
→ CLOSED_FOR_ODDS
```

Implemented:

- durable `pick_monitoring_states` with restart-safe MONITORING / CLOSED_FOR_ODDS state;
- append-only `pick_monitoring_transitions`;
- immutable `pick_closing_finalizations`;
- deterministic OPEN / ENTRY / CURRENT / CLOSE markers;
- same-game, same-bookmaker complete moneyline-pair closing selection;
- strict pre-kickoff quote eligibility;
- explicit closing outcomes:
  - `CAPTURED`;
  - `STALE_QUOTE`;
  - `NO_VALID_QUOTE`;
- active registered picks consume API refresh priority before broad market scanning;
- fresh single-game fixture evidence is checked before monitored odds refresh;
- after authoritative kickoff cutoff, a due pick finalizes without another odds request;
- monitoring and broad collection share the same per-run API request counter;
- broad odds-call capacity is reduced by monitored-pick odds calls already consumed;
- runtime health exposes monitored-pick and closing-finalization counts.

Verification evidence:

- global Baseball compile / Ruff format / Ruff lint / pytest: **SUCCESS**;
- Railway PostgreSQL smoke: **SUCCESS**;
- PostgreSQL integration proves registration → monitoring → quote history → closing → lifecycle markers;
- closing domain tests prove fresh, stale and missing-quote outcomes;
- active-pick unit tests prove fixture refresh precedes exact-bookmaker odds refresh;
- active-pick unit tests prove post-cutoff finalization does not issue a new odds call;
- shared PostgreSQL integration tests were made baseline-relative so test ordering cannot create false failures;
- focused Railway smoke now includes Package C runtime modules and tests in format, lint and pytest gates.

Safety:

- no real-money execution was added;
- no automatic staking was added;
- production collection remains disabled;
- no football Railway project or football repository was modified.

Next package:

> Package D — deterministic settlement / CLV evaluation and operational dashboard projections over the immutable pick + closing lifecycle.

## 46. Package D — authoritative settlement, realized CLV and operational projections — 2026-09-25

Completed the fourth QuantBet-parity vertical slice on branch `finish/settlement-clv-dashboard-20260925`.

Before Package D implementation, Package C production deployment was re-audited on Railway project `believable-contentment`:

- deployment `1cc8cd65-238e-4c50-986c-9882ab39e281`: **SUCCESS**;
- production deploy log explicitly applied `005_moneyline_monitoring_closing.sql`;
- subsequent cron invocations remained `collection_enabled=false` and `mode="storage-ready"`.

Implemented migration `006_moneyline_settlement_clv.sql` and the post-game lifecycle:

```text
registered paper pick
→ immutable closing finalization
→ authoritative provider game refresh
→ append-only final result fact
→ deterministic WIN / LOSS / PUSH settlement
→ realized CLV when exact closing evidence is CAPTURED
→ explicit unavailable CLV when close is stale or missing
→ read-only pick and dashboard projections
```

Implemented:

- append-only `game_result_facts` with exact final fixture observation and raw-payload provenance;
- immutable one-time `pick_settlements` referencing the registered pick, result fact and closing finalization;
- deterministic paper P&L per unit:
  - WIN = `entry_odds - 1`;
  - LOSS = `-1`;
  - PUSH = `0`;
- exact closing-pair de-vigging before CLV evaluation;
- realized CLV metrics only when closing outcome is `CAPTURED`:
  - closing market probability;
  - probability delta versus entry market probability;
  - entry/closing price ratio;
- explicit non-computable CLV states:
  - `UNAVAILABLE_STALE_QUOTE`;
  - `UNAVAILABLE_NO_VALID_QUOTE`;
- no interpolation, synthetic closing line or fabricated CLV;
- restart-safe/idempotent result and settlement persistence;
- post-game settlement refresh priority before active-pick monitoring and broad market collection;
- shared API client/request budget across settlement, monitoring and broad collection;
- `baseball_moneyline_pick_projection` read model;
- `baseball_moneyline_dashboard` read model for settlement, paper P&L and CLV coverage;
- runtime health counts for result facts, settled picks and available CLV.

Verification evidence:

- global Baseball compile / Ruff format / Ruff lint / pytest: **SUCCESS**;
- Railway PostgreSQL smoke: **SUCCESS**;
- domain tests prove WIN/LOSS/PUSH settlement semantics;
- domain tests prove stale/missing closes cannot manufacture CLV;
- settlement-loop tests prove non-terminal provider games do not settle;
- PostgreSQL integration proves registration → monitoring → closing → final result → settlement → CLV → dashboard projection;
- settlement replay is deterministic and idempotent;
- focused Railway smoke explicitly covers Package D source files, migration and tests.

Safety:

- no real-money execution was added;
- no automatic staking was added;
- production collection remains disabled;
- no football Railway project or football repository was modified.

Next package:

> Package E — canary/operational acceptance, settled-pick performance evaluation, CLV diagnostics and the explicit production collection enablement gate. Collection must remain disabled until that gate passes.



## 47. Package E — operational acceptance / canary gate started — 2026-09-25

Package D was independently verified after merge before starting Package E.

Verified Package D production evidence:

- PR #8 `Finish Package D: settlement CLV and dashboard projections` is merged;
- Package D head CI:
  - `Baseball tests`: **SUCCESS**;
  - `Railway runtime smoke`: **SUCCESS**;
- main commit: `0f1126fec305de58562c5551b0d81f36df7a2b9a`;
- Baseball Railway deployment: `1fc35c1d-9c1c-4843-b52e-154cb60411f9`;
- Railway deployment status: **SUCCESS**;
- deploy log explicitly applied:
  - `006_moneyline_settlement_clv.sql`;
- later cron runs remain:
  - `collection_enabled=false`;
  - `mode="storage-ready"`;
  - `status="ready"`.

Package E branch:

- `finish/package-e-canary-acceptance-20260925`.

Package E objectives:

1. machine-readable operational activation gate;
2. bounded one-shot canary mode distinct from scheduled production collection;
3. settled-pick performance evaluation;
4. CLV coverage / diagnostics;
5. explicit evidence for why scheduled collection is READY or BLOCKED;
6. keep scheduled collection disabled until the gate is proven.

Important finding discovered during Package E audit:

> The old `BASEBALL_MAX_ODDS_REQUESTS=76` budget was calibrated around 2 schedule requests + 76 odds requests per 15-minute cycle, which is 78 requests/cycle × 96 cycles/day = 7,488 requests/day. Package C and D added monitoring and settlement provider calls. Those calls share the same API client but are not all subtracted from the old broad-odds cap. Therefore the new worst-case request budget can exceed the 7,500/day subscription ceiling.

This means the activation gate must remain BLOCKED until a shared total per-cycle provider request cap is implemented.

Required Package E correction:

- bound **all fresh provider attempts** through one total cycle cap;
- include retries because `BaseballAPIClient.request_count` increments per HTTP attempt;
- prioritize settlement and active-pick monitoring;
- give broad schedule/odds collection only the remaining capacity;
- make daily worst-case request math mechanically auditable.

Safety:

- no production collection variable has been enabled;
- no canary has been executed yet;
- no football repository or Railway project has been modified.


### Package E implementation checkpoint — 2026-09-25

Implemented on `finish/package-e-canary-acceptance-20260925`:

- shared **75 total provider attempts/cycle** hard cap;
- 15-minute worst-case budget reduced to 7,200/day;
- 300/day theoretical headroom against the 7,500 subscription budget;
- default activation reserve requirement of 250/day;
- all retries and lifecycle/broad requests share the same request counter;
- broad odds capacity now consumes only what remains after settlement + monitoring and two reserved schedule calls;
- explicit `SCHEDULED` / `CANARY` collection-cycle execution modes;
- migration `007_operational_acceptance.sql`;
- immutable canary-run evidence;
- immutable activation-gate assessments;
- performance/CLV diagnostic SQL projections;
- bounded explicit canary runner;
- machine-readable CANARY and SCHEDULED_COLLECTION gates;
- unit + PostgreSQL integration tests;
- Railway smoke workflow coverage;
- `.env.example` activation/budget controls.

No production canary has been executed and `BASEBALL_ENABLE_COLLECTION` remains disabled.

Next gate:

> Global CI + Railway PostgreSQL smoke must be green before PR merge or any production canary.


### Package E CI iteration 1

PR #9 initial global test run failed only at Ruff formatting.

Fixed:

- `activation_gate.py` formatting;
- shared-cycle budget test formatting.

Compilation was already green. Lint/pytest were not reached in that run.

Failure and exact fixes are recorded in `docs/progress/2026-09-25-package-e-operational-acceptance.md`.

Production collection remains disabled.
