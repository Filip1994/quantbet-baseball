

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


### Package E CI iteration 2

Second PR #9 global run passed compile + formatting and failed Ruff lint on two blind `Exception` catches in `canary.py`.

Fixed in `0b705da`:

- expected operational errors are narrowly classified;
- unexpected programmer errors now propagate;
- failed-canary persistence fallback only catches PostgreSQL driver errors.

Full detail is recorded in `docs/progress/2026-09-25-package-e-operational-acceptance.md`.

No production canary was run. Scheduled collection remains disabled.


### Package E code gates green — 2026-09-25

Package E code head `2129cf4` passed:

- global Baseball tests run `36154788452`: **SUCCESS**;
- Railway/PostgreSQL smoke run `36154788449`: **SUCCESS**.

Package E is ready for merge from a code/CI perspective.

Activation remains deliberately separate:

- no production canary has been run;
- `BASEBALL_ENABLE_CANARY` has not been enabled;
- `BASEBALL_ENABLE_COLLECTION` remains disabled.

After merge: verify migration 007 in Baseball Railway, then run the read-only CANARY readiness assessment before any canary execution.


### Package E production deploy + gate runtime hotfix — 2026-09-25

Verified:

- Package E main commit: `d1e7b82f5006507200f6f9ebe652e60533455538`;
- Baseball Railway deployment `26d1ed34-70d7-4aaa-a23f-e0452ac35133`: **SUCCESS**;
- production deploy log applied `007_operational_acceptance.sql`.

Production prerequisite audit found:

- PostgreSQL present;
- raw archive variable set complete;
- `API_BASEBALL_KEY` missing.

An operational reachability gap was also found: Railway exposes no arbitrary `exec` into the deployed cron container, so the activation-gate CLI could not be invoked without a config change.

Hotfix branch `package-e-gate-runtime-20260925` now makes the storage-ready worker automatically persist and emit the CANARY readiness verdict while scheduled collection is OFF.

No provider API call is made by that assessment. Collection and canary remain disabled.


### Gate runtime hotfix CI green

PR #10 head `5a135926f` passed:

- Baseball tests `36155704541`: SUCCESS;
- Railway/PostgreSQL smoke `36155704549`: SUCCESS.

After merge, production acceptance requires observing the next storage-ready cron's persisted activation verdict. Expected blocker remains `API_KEY_MISSING`.


## 55. Mainline reconciliation and obsolete duplicate branch — 2026-09-25

While the assistant was continuing Package D on branch `finish/settlement-clv-dashboard-20260925`, Baseball `main` advanced independently.

Verified newer main commits:

- `0f1126fec305de58562c5551b0d81f36df7a2b9a` — Finish Package D: settlement CLV and dashboard projections;
- `d1e7b82f5006507200f6f9ebe652e60533455538` — Finish Package E: operational canary and activation gate;
- `fdaf67048ac776a31774421c0f9fe31987890e8b` — Hotfix Package E gate runtime reachability.

The duplicate Package D PR #11 was therefore closed **without merge**.

Reason:

- branch merge base was Package C commit `8bb4aed...`;
- branch was behind current main by three commits;
- current main already contained the authoritative Package D implementation and the subsequent Package E implementation/hotfix;
- merging the duplicate branch would risk regressing newer operational-gate work.

This is a reconciliation correction, not a production rollback.

## 56. Package E production deployment and live gate evidence — 2026-09-25

Verified Baseball Railway target only:

- project: `believable-contentment`;
- service: `quantbet-baseball`;
- latest completed deployment before config correction:
  - `5a841e0d-4ff7-41d1-8ffa-c4699952dadd`;
  - commit: `fdaf67048ac776a31774421c0f9fe31987890e8b`;
  - status: **SUCCESS**.

Storage-ready runtime log emitted a persisted CANARY readiness assessment.

Observed live verdict:

- target: `CANARY`;
- verdict: `BLOCKED`;
- reason codes:
  - `API_BUDGET_UNSAFE`;
  - `API_KEY_MISSING`;
- collection enabled: `false`;
- paper mode: `true`;
- raw archive configured: `true`;
- migrations current: `true`;
- runtime fresh: `true`;
- recent successful canary: `false`.

Observed budget projection before correction:

- daily request budget: **78**;
- cycle request cap: **75**;
- cron interval: **15 minutes**;
- cycles/day: **96**;
- worst-case daily requests: **7,200**;
- required reserve: **250**;
- request headroom: **-7,122**.

This exposed production configuration drift:

> `BASEBALL_API_REQUEST_BUDGET` still contained the historical per-run value `78`, while Package E now defines that variable as the provider daily request ceiling.

Repository configuration and Package E design both define the intended daily ceiling as **7,500**.

A Railway variable-name audit also confirmed:

- `API_BASEBALL_KEY` is absent;
- no alternate provider-key variable exists on the Baseball service;
- secret values were not exposed.

## 57. Package E production budget config correction — 2026-09-25

Corrected Baseball Railway production variable:

- `BASEBALL_API_REQUEST_BUDGET`:
  - old: `78`;
  - new: `7500`.

Only the Baseball service in `believable-contentment` was changed.

Not changed:

- `BASEBALL_ENABLE_COLLECTION`;
- `BASEBALL_ENABLE_CANARY`;
- `PAPER_MODE`;
- raw archive credentials/configuration;
- football project/repository.

Railway automatically started deployment:

- deployment: `ea40064f-a02c-4228-9d1f-5792402e48e2`;
- commit remains `fdaf67048ac776a31774421c0f9fe31987890e8b`;
- status at the time of this log entry: `INITIALIZING`.

Expected gate effect after successful redeploy:

- `API_BUDGET_UNSAFE` should disappear;
- expected remaining blocker: `API_KEY_MISSING`;
- collection must remain disabled.

This expectation is not treated as verified until the post-redeploy runtime log is inspected.


## 58. Budget-fix redeploy success and cron verification boundary — 2026-09-25

Railway deployment triggered by the production budget-variable correction completed successfully:

- deployment: `ea40064f-a02c-4228-9d1f-5792402e48e2`;
- commit: `fdaf67048ac776a31774421c0f9fe31987890e8b`;
- status: **SUCCESS**.

Deploy-time logs show migrations are already current:

- `migrations_applied: ()`.

Because `quantbet-baseball` is a Railway cron service, a redeploy does not itself execute the scheduled worker body. Therefore this deployment log does not yet contain the post-fix `activation_gate` assessment.

A Railway capability check confirmed there is no supported non-mutating one-shot cron invocation mechanism. Available alternatives would require waiting for the next scheduled run or mutating/redeploying service behavior.

Decision:

- do not alter cron configuration;
- do not add a temporary service/function;
- do not enable canary;
- do not enable collection;
- wait for the normal 15-minute Baseball cron execution to produce the next persisted readiness assessment.

Expected but **not yet verified** post-fix gate state:

- `API_BUDGET_UNSAFE` removed;
- `API_KEY_MISSING` remains;
- verdict remains `BLOCKED`;
- `BASEBALL_ENABLE_COLLECTION=false`.


## 59. Documentation-only deploy noise and watch-pattern hardening attempt — 2026-09-25

After operational documentation PR #12 merged as:

- `cc31a5dc0cfa525d4bccac7b90ea247cb94d1ae6`;

Railway automatically started another `quantbet-baseball` deployment even though the commit changed only Markdown documentation.

Observed deployment:

- `1466ff80-d238-4f38-9822-c4098fafc9da`;
- reason: GitHub deploy from docs-only main commit;
- status at this log entry: `BUILDING`.

This indicates the Baseball Railway service currently has no effective runtime-file watch filter.

Proposed runtime-relevant watch patterns:

- `src/**`;
- `migrations/**`;
- `requirements.txt`;
- `requirements-dev.txt`;
- `pyproject.toml`.

Purpose:

- prevent documentation/progress-only commits from causing unnecessary production builds/deployments;
- preserve deploys for runtime code, migrations and dependency changes.

Attempt history:

1. first Railway `update_service` call used an incorrect environment identifier and was rejected; no configuration changed;
2. corrected call used the proper Baseball production environment identifier but was blocked by the tool safety layer before execution; no configuration changed.

Therefore:

> Railway watch patterns remain unchanged.

No attempt was made to bypass the safety block.

Production collection and canary remain disabled.


## 60. Independent Package E migration verification — 2026-09-25

Independently re-read Railway deploy logs for Package E deployment:

- deployment: `26d1ed34-70d7-4aaa-a23f-e0452ac35133`;
- commit: `d1e7b82f5006507200f6f9ebe652e60533455538`.

Railway deploy log explicitly reports:

- `007_operational_acceptance.sql` applied.

This independently confirms the Package E operational-acceptance schema exists in Baseball production.

The current blocker is not migration state. It is runtime provider configuration:

- budget config drift was corrected to 7,500;
- `API_BASEBALL_KEY` remains absent;
- collection remains disabled.


## 61. Post-budget-fix natural cron acceptance evidence — 2026-09-25

Scope remained Baseball production only:

- Railway project: `believable-contentment` (`089895e8-c4b7-4f3b-9fb9-ca9be11544f4`);
- environment: `production` (`32ceeb6e-a8a8-4f98-b757-58d63417e496`);
- service: `quantbet-baseball` (`e6f5221e-0165-4bb6-9daf-9525ae8ebc5f`);
- football repository/project untouched.

### Docs-only deployment final status

The previously observed docs-only deployment is now terminal:

- deployment: `1466ff80-d238-4f38-9822-c4098fafc9da`;
- commit: `cc31a5dc0cfa525d4bccac7b90ea247cb94d1ae6`;
- status: **SUCCESS**.

The service configuration still reports:

- cron: `*/15 * * * *`;
- source repository: `Filip1994/quantbet-baseball`;
- source branch: `main`;
- watch patterns: not configured.

No watch-pattern mutation was attempted.

### First natural cron after the budget correction

The first normal scheduled execution observed after the production budget correction ran on the current deployment at:

- container start: `2026-09-25T16:15:46.860128915Z`;
- gate/runtime evidence: `2026-09-25T16:15:48.524278955Z`;
- Europe/Belgrade local time: approximately `2026-09-25 18:15:48 +02:00`;
- activation assessment ID: `93f7b3b6-c297-52ed-8ddb-ba31c5688bd1`.

Persisted/logged CANARY-target gate evidence:

- `daily_request_budget=7500`;
- `cycle_request_cap=75`;
- `cycles_per_day=96`;
- `worst_case_daily_requests=7200`;
- `request_headroom=300`;
- `daily_reserve_required=250`;
- `api_key_configured=false`;
- `canary_passed=false`;
- `collection_enabled=false`;
- `migrations_current=true`;
- `paper_mode=true`;
- `raw_archive_configured=true`;
- `runtime_fresh=true`;
- reason codes: **[`API_KEY_MISSING`]**;
- verdict: **`BLOCKED`**;
- runtime mode: `storage-ready`.

Therefore the expected correction is now proven from a real scheduled execution:

- `API_BUDGET_UNSAFE` is absent;
- `API_KEY_MISSING` remains;
- the gate remains correctly fail-closed;
- scheduled collection remains OFF;
- no canary is armed or passed;
- no provider request can be fabricated without the missing credential.

### Stability check

Later natural cron executions continued to emit the same safe budget and blocker state. The latest inspected execution was:

- evidence timestamp: `2026-09-25T21:15:17.162099029Z` (`23:15:17 +02:00`);
- assessment ID: `870a6ef0-fcbf-5a06-a5dc-cc760a8c8a74`;
- reason codes: **[`API_KEY_MISSING`]**;
- verdict: **`BLOCKED`**;
- `collection_enabled=false`.

Production acceptance is now blocked solely by the absent provider credential, not by Package A-E code, migrations, runtime freshness, archive configuration, paper-mode safety, or API budget arithmetic.


## 62. Post-logging safety read-back — 2026-09-25

After writing the post-budget-fix cron evidence, a read-only safety verification confirmed:

- PR #13 remains **open** and **unmerged**;
- PR branch: `ops/package-e-deploy-watchpaths-20260925`;
- PR head at verification: `6eaf6c251cbeaba70ba7a393c9e65a6acca459d4`;
- base branch: `main`;
- base SHA remains `cc31a5dc0cfa525d4bccac7b90ea247cb94d1ae6`;
- branch is 4 commits ahead and 0 behind;
- exactly two files differ from main:
  - `BASEBALL_PROGRESS.md`;
  - `docs/progress/2026-09-25-package-e-operational-acceptance.md`.

Railway production also remains unchanged:

- latest deployment is still `1466ff80-d238-4f38-9822-c4098fafc9da`;
- status: `SUCCESS`;
- deployed commit: `cc31a5dc0cfa525d4bccac7b90ea247cb94d1ae6`;
- source branch: `main`.

Therefore the audit logging work did **not** mutate Baseball production and did not merge PR #13.


## 63. Package E handoff revalidation — 2026-09-26

Performed a fresh read-only Baseball production revalidation for the current handoff.

Railway scope remained strictly:

- project: `believable-contentment` (`089895e8-c4b7-4f3b-9fb9-ca9be11544f4`);
- environment: `production` (`32ceeb6e-a8a8-4f98-b757-58d63417e496`);
- service: `quantbet-baseball` (`e6f5221e-0165-4bb6-9daf-9525ae8ebc5f`).

No football repository or Railway project was modified.

Fresh verification:

- current Baseball deployment `1466ff80-d238-4f38-9822-c4098fafc9da` is `SUCCESS`;
- deployment source remains main commit `cc31a5dc0cfa525d4bccac7b90ea247cb94d1ae6`;
- cron remains `*/15 * * * *`;
- service source remains `Filip1994/quantbet-baseball` branch `main`;
- no watch patterns are configured in the returned service config;
- production variable names still do **not** include `API_BASEBALL_KEY`.

The latest completed natural cron visible in this revalidation emitted gate evidence at
`2026-09-25T22:00:51.824842688Z` (local Europe/Belgrade date: 2026-09-26), assessment
`f940b8d9-0240-5269-b0be-5ebf532de2e7`.

Its activation gate again reports:

- `daily_request_budget=7500`;
- `cycle_request_cap=75`;
- `cycles_per_day=96`;
- `worst_case_daily_requests=7200`;
- `request_headroom=300`;
- `daily_reserve_required=250`;
- `api_key_configured=false`;
- `canary_passed=false`;
- `collection_enabled=false`;
- `migrations_current=true`;
- `paper_mode=true`;
- `raw_archive_configured=true`;
- `runtime_fresh=true`;
- reason codes: `[API_KEY_MISSING]`;
- verdict: `BLOCKED`.

Therefore the post-budget-fix acceptance conclusion remains stable:

- `API_BUDGET_UNSAFE` is absent;
- the budget correction is still effective;
- the only live CANARY-target blocker is the missing provider credential;
- scheduled collection remains disabled;
- no canary was armed or executed.

No Railway configuration mutation, redeploy, cron mutation, canary action, collection activation, or PR merge was performed during this revalidation.


## 64. Provider-key handoff check — 2026-09-26

The operator reported that the Baseball provider credential had been added in Railway.

A fresh read-only check was performed against the guarded Baseball production scope only.

Observed immediately after the reported change:

- a new deployment exists: `59cccc85-cc41-45aa-8b46-9760c3945cd6`;
- deployment state progressed from `WAITING` to `BUILDING`;
- service/environment IDs match the guarded Baseball production target;
- however, the effective variable-name inventory returned for `quantbet-baseball` still does **not** contain `API_BASEBALL_KEY`;
- `get_service_config` also does not list `API_BASEBALL_KEY` among direct service variable names;
- no canary was armed and scheduled collection remains unchanged.

Decision:

> Do not arm the canary until the credential is independently visible to the Baseball service and a natural storage-ready gate reports CANARY readiness.

This is treated as an unresolved Railway variable-scope/application check, not as a reason to bypass the activation gate.


## 65. Provider URL restored after credential misplacement — 2026-09-26

The operator identified that the provider API key had been pasted into `API_BASEBALL_BASE_URL` instead of a new `API_BASEBALL_KEY` variable.

Repository configuration was re-read and confirms the canonical Baseball provider base URL is:

- `https://v1.baseball.api-sports.io`.

Production correction applied only to the guarded Baseball service:

- restored `API_BASEBALL_BASE_URL=https://v1.baseball.api-sports.io`;
- used a no-redeploy variable update;
- did not set or invent `API_BASEBALL_KEY`;
- did not enable canary;
- did not enable scheduled collection;
- did not change cron or paper mode.

The remaining operator action is to create `API_BASEBALL_KEY` on the same Baseball production service with the actual provider credential.

After that, the next required sequence remains:

1. verify the key name is visible to the service;
2. let Railway deploy naturally;
3. require the storage-ready activation gate to become ready for CANARY;
4. only then arm one bounded canary.


## 66. Provider credential visible on guarded Baseball service — 2026-09-26

Fresh Railway verification now confirms that `API_BASEBALL_KEY` is present in the effective variable-name inventory for the guarded `quantbet-baseball` production service.

Observed deployment triggered by the credential change:

- deployment: `667487c1-6b31-4624-ae36-a655147b6f08`;
- state at first inspection: `WAITING`;
- source remains main commit `cc31a5dc0cfa525d4bccac7b90ea247cb94d1ae6`.

Safety state at this checkpoint:

- scheduled collection remains disabled;
- no canary has been armed or executed;
- the next required evidence is a natural storage-ready activation-gate result with `api_key_configured=true` and a CANARY-ready verdict.

No football resource was touched.


## 67. Provider credential deployment success; natural gate pending — 2026-09-26

The deployment triggered after the correctly named provider credential was added has completed:

- deployment: `667487c1-6b31-4624-ae36-a655147b6f08`;
- status: **SUCCESS**;
- source commit: `cc31a5dc0cfa525d4bccac7b90ea247cb94d1ae6`;
- pre-deploy migration output: no new migrations applied.

Runtime safety remains unchanged:

- `API_BASEBALL_KEY` is visible to the guarded Baseball service;
- `BASEBALL_ENABLE_COLLECTION` has not been enabled;
- no canary has been armed or executed;
- cron remains `*/15 * * * *`;
- no start-command or cron mutation was used to force execution.

The deployment startup itself is not accepted as the CANARY readiness proof. The next required evidence remains the first natural cron worker run on this deployment.

A one-time follow-up check was scheduled for the next cron window so the acceptance sequence can continue without manual schedule mutation. That follow-up is constrained to the same Baseball project/service and must not alter football resources or merge PR #13.


## 67. Natural CANARY gate is READY; research scope clarified — 2026-09-26

Fresh production evidence from deployment `667487c1-6b31-4624-ae36-a655147b6f08` confirms the guarded Baseball service is ready for a bounded canary.

Natural cron evidence:

- `2026-09-25T22:46:09.281100553Z` — assessment `4d728848-a171-5bd0-8ff6-433df8ea642c`;
- `2026-09-25T23:00:25.018291765Z` — assessment `06819072-49ea-5308-b4ce-6c44b69b2c45`;
- target: `CANARY`;
- verdict: `READY`;
- reason codes: none;
- `api_key_configured=true`;
- `collection_enabled=false`;
- `paper_mode=true`;
- `migrations_current=true`;
- `raw_archive_configured=true`;
- `runtime_fresh=true`;
- daily budget 7500, cycle cap 75, worst-case 7200, reserve 250, headroom 300.

The research product scope was also clarified:

- no player-prop betting product;
- initial product remains game-level moneyline research and paper picks;
- fixed paper stake target: 300 RSD per registered single;
- preserve full raw provider payloads;
- canonically ingest pregame variables that are useful to game-level prediction when the provider exposes them;
- add point-in-time weather where available and relevant, with roof/venue handling;
- do not blindly promote every raw field into a model feature: retain everything, then admit features through availability/leakage checks.

Next engineering step: implement a DB-idempotent one-shot canary path in the existing cron worker. It must run at most once while a recent PASSED canary exists, remain bounded to the configured canary request caps, and keep scheduled collection disabled.


## 68. One-shot canary merged and armed — 2026-09-26

Production-readiness work advanced from gate-only evidence to a bounded executable canary path.

Code evidence:

- PR #14 `Add idempotent one-shot Baseball canary execution` passed both Baseball tests and Railway runtime smoke;
- PR #14 was squash-merged to `main` as commit `dd423761e9146c1ea674a483ae8b12c3fe84fc50`;
- production deployment `26d1fbdd-7389-4ad4-b9b4-691aefcb2fcb` reached `SUCCESS` on that commit;
- PR #13 remains separate and unmerged.

One-shot semantics now enforced by the worker:

- canary executes only when explicitly armed;
- CANARY activation gate must be READY;
- scheduled collection and canary cannot run together;
- a recent persisted PASSED canary causes later armed cycles to return `ALREADY_PASSED` rather than rerun provider requests;
- successful canary causes a separate `SCHEDULED_COLLECTION` gate assessment;
- cron and production start command were not changed.

Production variables were then explicitly set on only the guarded Baseball service:

- `BASEBALL_ENABLE_CANARY=true`;
- `BASEBALL_CANARY_MAX_API_REQUESTS=8`;
- `BASEBALL_CANARY_MAX_ODDS_REQUESTS=2`;
- `BASEBALL_CANARY_MAX_MONITORING_REFRESHES=1`;
- `BASEBALL_CANARY_MAX_SETTLEMENT_REFRESHES=1`;
- `BASEBALL_ENABLE_COLLECTION=false`;
- `PAPER_MODE=true`.

Railway created variable redeployment `b7c0a7ea-5a76-464e-8efe-81187b3a3634`. No production canary result is claimed until a natural cron run records the persisted canary evidence.


## 69. First live bounded canary failed safely on canonical odds mapping — 2026-09-26

The first armed production canary executed naturally on deployment `b7c0a7ea-5a76-464e-8efe-81187b3a3634` at `2026-09-25T23:16:05.657939242Z`.

Pre-run CANARY gate remained `READY` with no blocker codes and all safety checks green.

Canary fact:

- canary ID: `e52931fc-e7ab-56cc-be44-9f175c20f1e8`;
- collection cycle: `dbddfcb8-6a6f-412b-b46a-017b986286f3`;
- status: `FAILED`;
- provider requests: 4 of maximum 8;
- games seen: 66;
- pregame games: 38;
- games selected for odds: 2;
- odds calls: 2;
- raw market rows observed: 1387;
- fixture observations inserted: 66;
- canonical odds rows: 0;
- odds observations inserted: 0;
- provider/collector errors: 0;
- reason codes: `POSTGRES_WRITES_NOT_VERIFIED`, `RAW_ARCHIVE_NOT_VERIFIED`;
- scheduled collection remained disabled;
- paper mode remained enabled.

Health after the canary proves fixture persistence worked: 66 distinct fixtures / 66 fixture observations and one collection cycle are present. The failure is therefore downstream of successful provider access and fixture ingestion, specifically at the live odds canonicalization/persistence boundary. The system correctly failed closed and scheduled collection must remain OFF until this mapper/provenance issue is repaired and a fresh bounded canary passes.


## 70. Failed canary disarmed; live moneyline mapper repair in review — 2026-09-26

Because the first canary FAILED, the one-shot guard correctly did not mark it as completed. To prevent repeated quota use on later cron cycles, production was explicitly returned to:

- `BASEBALL_ENABLE_CANARY=false`;
- `BASEBALL_ENABLE_COLLECTION=false`;
- `PAPER_MODE=true`.

The resulting Railway deployment `2c42711f-e4b2-4410-a05f-407cdb767113` reached `SUCCESS`.

Mapper diagnosis found a concrete compatibility gap: the strict full-game moneyline allowlist did not include API-Sports' two-way `Home/Away` market label. A repair was opened as PR #15, `Fix live API-Sports Baseball moneyline mapping`, head `392858ae53714c3c7e3dfb272f80c0350537d8b1`.

The repair also removes legacy player-prop target tokens from compact market targeting while preserving the complete raw provider response in object storage. Bounded market/bookmaker-name diagnostics are added so the next canary reports the actual live provider labels rather than relying on assumptions.

No collection activation will occur before PR #15 passes CI, deploys, and a fresh bounded canary passes.
