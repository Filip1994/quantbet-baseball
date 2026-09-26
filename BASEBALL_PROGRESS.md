

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


## 69. First live canary failed safely at canonical odds ingestion — 2026-09-26

Natural cron on deployment `b7c0a7ea-5a76-464e-8efe-81187b3a3634` executed the bounded canary at `2026-09-25T23:16:05.657939242Z`.

Observed canary evidence:

- canary id: `e52931fc-e7ab-56cc-be44-9f175c20f1e8`;
- collection cycle id: `dbddfcb8-6a6f-412b-b46a-017b986286f3`;
- execution mode: `CANARY`;
- status: `FAILED`;
- provider attempts: 4 of max 8;
- schedule/game discovery: 66 games seen, 38 pregame games, 2 games selected;
- fixture observations inserted: 66;
- odds calls: 2;
- compact raw market value rows observed: 1387;
- canonical odds rows: 0;
- PostgreSQL odds observations inserted: 0;
- provider/API errors: 0;
- failure reasons: `POSTGRES_WRITES_NOT_VERIFIED`, `RAW_ARCHIVE_NOT_VERIFIED`.

Interpretation: provider connectivity, raw schedule ingestion, fixture canonicalization and raw odds retrieval all worked. The failure is localized to the strict moneyline canonicalization path: the odds payload produced many market rows but none matched the current canonical moneyline contract, so the canary correctly refused activation.

Immediate safety action:

- `BASEBALL_ENABLE_CANARY=false` was set after the failed run;
- `BASEBALL_ENABLE_COLLECTION=false` was reasserted;
- `PAPER_MODE=true` was reasserted;
- Railway deployed this safe state as `2c42711f-e4b2-4410-a05f-407cdb767113`, commit `dd423761e9146c1ea674a483ae8b12c3fe84fc50`, status SUCCESS.

No scheduled collection is authorized. Next step is exact market-schema diagnostics, then a parser fix proven by tests and a second bounded canary.


## 70. Canary-only odds schema probe merged — 2026-09-26

To avoid widening the production moneyline parser based on guesses, PR #16 added a CANARY-only schema probe. The probe records only distinct market names and candidate selection labels in the canary summary; it deliberately excludes odds/prices and secrets. It does not change canonical ingestion, pick selection, cron cadence, API budget, or scheduled collection behavior.

Validation:

- initial formatting check failed and no merge occurred;
- formatting was corrected on the branch;
- Baseball tests then passed;
- Railway runtime smoke then passed;
- PR #16 was squash-merged to `main` as `e0f2926287c4dd269a499249f3645f684e2d048a`.

Production remains safe pending Railway deployment of that commit: canary disabled, scheduled collection disabled, paper mode required. After deployment success, one bounded diagnostic canary may be re-armed with the existing 8/2/1/1 caps to capture the exact live market labels responsible for the zero-canonical-row failure.


## 70. Canary schema probe deployed and re-armed — 2026-09-26

PR #16 `Add canary-only odds schema probe` passed Baseball tests and Railway runtime smoke and was merged to main as `e0f2926287c4dd269a499249f3645f684e2d048a`.

Production deployment `d60fd5df-7b4d-495d-8255-aa2eb19edee7` reached `SUCCESS` on that commit.

The guarded Baseball service was then re-armed for exactly one bounded diagnostic canary with:

- `BASEBALL_ENABLE_CANARY=true`;
- `BASEBALL_CANARY_MAX_API_REQUESTS=8`;
- `BASEBALL_CANARY_MAX_ODDS_REQUESTS=2`;
- `BASEBALL_CANARY_MAX_MONITORING_REFRESHES=1`;
- `BASEBALL_CANARY_MAX_SETTLEMENT_REFRESHES=1`;
- `BASEBALL_ENABLE_COLLECTION=false`;
- `PAPER_MODE=true`.

The diagnostic code records only distinct market names and candidate selection labels during CANARY execution. It does not log prices, credentials, or widen production canonicalization. The next natural cron is required to provide the exact provider market schema before any parser change is accepted.


## 71. Second bounded schema-diagnostic canary armed — 2026-09-26

After PR #16 merged the CANARY-only market-schema probe, Railway deployment `cb8f02d3-6894-4806-8e2d-da279bd9dc2a` reached SUCCESS on commit `e0f2926287c4dd269a499249f3645f684e2d048a`. A second bounded diagnostic canary was then armed with the same strict caps: 8 total provider attempts, 2 broad odds requests, 1 monitoring refresh, and 1 settlement refresh. Scheduled collection remains disabled and paper mode remains required.

The variable redeployment is `d60fd5df-7b4d-495d-8255-aa2eb19edee7`; it reached SUCCESS on the same commit. The next natural cron is expected to expose only distinct market names and candidate selection labels in addition to the normal canary telemetry. No parser widening is authorized until that live schema evidence exists. Cron/start command were not changed and no helper service was created.

In parallel, draft PR #17 was opened for the immutable pregame feature-snapshot contract. It is deliberately separate from operational acceptance and remains unmerged. The contract records source observed/available timestamps, archived payload provenance and feature paths, and rejects sources unavailable by the decision cutoff or snapshots generated at/after first pitch. This is the storage boundary for future verified Baseball and weather features; player-prop betting remains excluded.


## 72. Game-level feature and weather foundations staged — 2026-09-26

Model/data work continued without changing production activation state.

Draft PR #17 (`Add immutable pregame feature snapshot contract`) establishes a replayable point-in-time feature boundary for game-level Baseball predictions. It records provider/source type, observed and available timestamps, raw payload ref/checksum, feature paths, decision cutoff, generation time and first pitch. Sources unavailable by the cutoff and snapshots generated at/after first pitch fail closed. PostgreSQL migration `008_pregame_feature_snapshots.sql` is included. Baseball tests and Railway runtime smoke both passed. PR #17 remains draft and unmerged while odds ingestion acceptance is unresolved.

Draft PR #19 (`Add point-in-time stadium weather capture`) is also staged independently. It uses Open-Meteo forecast evidence at supplied stadium coordinates, archives the raw response in a separate `open-meteo` namespace, selects the weather sample nearest first pitch, and carries temperature, humidity, dew point, precipitation probability/amount, pressure, cloud cover, wind speed/direction/gusts plus explicit roof state. Closed-roof/dome contexts retain the evidence but mark weather as non-applicable to play. It is not wired into production picks or collection yet.

Player-prop betting remains excluded. Player/team information may later be admitted only as game-level model inputs when live Baseball provider coverage is actually verified.


## 71. Research weather and feature provenance foundation merged — 2026-09-26

PR #18 `Add point-in-time Baseball weather evidence contract` passed the Baseball test workflow and was squash-merged to main as `1f8b535f8a70b5f58a0db88e864c5f3a5b0902cf`.

Research-layer additions:

- Open-Meteo first-pitch forecast evidence at stadium coordinates;
- full raw weather response archival before canonicalization;
- roof-aware weather applicability (closed/fixed indoor roof skips weather);
- pregame-only weather cutoff enforcement;
- canonical weather fields for temperature, humidity, dew point, precipitation, pressure, cloud cover, wind speed/direction/gusts, and weather code;
- immutable feature-source and feature-snapshot provenance contracts;
- explicit raw-retain/model-admit policy in `docs/BASEBALL_RESEARCH_FEATURE_REGISTRY.md`;
- player statistics may only support game-level feature construction; player-prop betting remains excluded.

This merge does not integrate weather into the production collector, does not change pick thresholds, does not enable scheduled collection, and adds no database migration. Production remains paper-only. The main deploy created by this merge is also the next clean opportunity for the already configured bounded schema-probe canary to load its runtime variables naturally.


## 72. Second bounded canary: selected odds payloads contained no market rows — 2026-09-26

A second natural bounded canary executed at `2026-09-25T23:46:33.726660077Z` with the canary-only schema probe active.

Evidence:

- canary id: `e7e10245-4941-55c1-8cdd-f7b662047dca`;
- collection cycle: `eaf76e67-fea3-42e3-90ee-b40f8dddb488`;
- API requests: 4 of max 8;
- fixture observations inserted: 66;
- games seen: 66;
- pregame games: 35;
- games selected for odds: 2;
- odds calls: 2;
- provider/API errors: 0;
- raw market rows: 0;
- canonical rows: 0;
- PostgreSQL odds observations inserted: 0;
- schema market names: empty;
- schema candidate values: empty;
- status: `FAILED` with `POSTGRES_WRITES_NOT_VERIFIED` and `RAW_ARCHIVE_NOT_VERIFIED`.

This does **not** prove a moneyline market-name mismatch. Unlike the first canary, these two selected games exposed no compact market rows at all. The next diagnostic must distinguish an empty provider odds response from an unrecognized payload shape before changing canonical moneyline matching.

Safety action immediately after this result:

- `BASEBALL_ENABLE_CANARY=false`;
- `BASEBALL_ENABLE_COLLECTION=false`;
- `PAPER_MODE=true`.

Next bounded diagnostic design: record only response row counts and JSON key names (no odds/prices/secrets), and increase the diagnostic odds sample from 2 to at most 4 games while retaining the hard 8-request canary cap.


## 73. Live-history moneyline semantics corrected — 2026-09-26

Repository-held live API-Sports Baseball evidence established the exact full-game moneyline semantics before changing the parser.

Historical live evidence:

- `data/baseball/LIVE_API_AUDIT.md` records `Home/Away` in 496 snapshots and `Match Winner` in 489 snapshots;
- a stored MLB raw odds payload for game `185853` shows market id `1`, name `Home/Away`, with exactly two selections: `Home` and `Away`, across multiple bookmakers;
- stored MLB raw payloads also show market id `14`, name `Match Winner`, with three selections: `Home`, `Draw`, `Away`.

This exposed two canonicalization defects:

1. exact `Home/Away` was not accepted as moneyline and could be filtered out for non-local bookmakers;
2. three-way `Match Winner` could be partially canonicalized by dropping `Draw`, which is invalid for two-way de-vigging.

PR #22 `Canonicalize API-Sports Home/Away moneyline` passed Baseball tests and Railway runtime smoke and was squash-merged to main as `a4d20a9d624342a286603fe46bd2a4cf3dff3640`.

Fix semantics:

- `Home/Away` is retained by compact odds for all bookmakers and canonicalized as game-level moneyline;
- a candidate moneyline market is rejected as a whole when any outcome cannot map to home or away;
- therefore three-way `Match Winner` with `Draw` fails closed;
- innings variants remain excluded by exact market-name matching.

Scheduled collection remains disabled and paper mode remains mandatory. The next acceptance action is a third bounded live canary after this commit is successfully deployed, with at most 4 broad odds calls under the unchanged 8-request total canary cap.


## 74. Third bounded canary: parser fix deployed, but selected odds responses were empty — 2026-09-26

Main commit `a4d20a9d624342a286603fe46bd2a4cf3dff3640` was deployed successfully in Railway as deployment `b57c3196-98f1-48ef-9c63-65666ed9c264`.

The first natural cron after that successful deploy executed another bounded canary at `2026-09-26T00:16:00.231890365Z`.

Canary evidence:

- canary id: `6f337f6f-d35a-595d-9874-f5d909a5dca0`;
- cycle id: `88839d4c-7b40-4fe6-b3e4-c4d132339c19`;
- API requests: 6 of max 8;
- games seen: 64;
- pregame games: 49;
- games selected: 4;
- odds calls: 4;
- provider/API errors: 0;
- fixture observations inserted: 64;
- odds payload rows: 0;
- empty odds calls: 4;
- non-empty odds calls: 0;
- bookmaker records: 0;
- raw market rows: 0;
- canonical rows: 0;
- PostgreSQL odds observations inserted: 0;
- canary status: `FAILED`;
- reason codes: `POSTGRES_WRITES_NOT_VERIFIED`, `RAW_ARCHIVE_NOT_VERIFIED`.

Interpretation:

The Home/Away canonicalization fix is deployed, but this run did not exercise it because all four selected provider odds responses were empty. This means the current acceptance blocker is no longer a proven parser mismatch; it is now odds coverage/availability and/or event-selection timing for the sampled games.

Immediate safety action:

- `BASEBALL_ENABLE_CANARY=false`;
- `BASEBALL_ENABLE_COLLECTION=false`;
- `PAPER_MODE=true`.

Do not widen the parser further based on this result. The next investigation should determine why four selected pregame games had empty odds responses, using historical live payloads and provider coverage evidence before spending additional API budget.


## 75. Single-response games schema audit across MLB and other leagues — 2026-09-26

A fresh one-request provider diagnostic was attempted through the Railway agent, but Railway's agent security model does not expose `API_BASEBALL_KEY` or `API_BASEBALL_BASE_URL` values to the agent, so **zero new provider requests were made**.

Instead, one original archived API-Sports `/games` response already retained in the repository was audited as a single-response schema comparison:

- source: `data/baseball/raw_api/2026-09-14/20260914T202857.785122Z_games_6722c60d17a2750c.json`;
- provider request: `games?date=2026-09-14`;
- captured at: `2026-09-14T20:28:57.785309+00:00`;
- API results: 13;
- API errors: none.

League coverage in this one response:

- MLB (id 1): 7 games;
- NPB (id 2): 3 games;
- LMB (id 21): 1 game;
- PCL (id 4): 1 game;
- CPBL (id 29): 1 game.

The MLB rows and non-MLB rows exposed the same top-level game-record keys:

- `id`;
- `date`;
- `time`;
- `timestamp`;
- `timezone`;
- `week`;
- `status`;
- `country`;
- `league`;
- `teams`;
- `scores`.

Nested schemas were also the same across sampled leagues:

- league: `id,name,type,season,logo`;
- country: `id,name,code,flag`;
- teams: `home,away`, each with `id,name,logo`;
- status: `long,short`;
- scores: `home,away`.

In this endpoint response there were no fields for:

- injuries;
- probable or confirmed starting pitchers;
- lineups;
- weather;
- venue/stadium metadata;
- stadium coordinates;
- roof state;
- umpire;
- player statistics.

No MLB-only top-level fields were found, and no non-MLB-only top-level fields were found in this single response.

Interpretation: the generic `/games` endpoint is schedule/result metadata and does not by itself provide the rich pregame context required by the research model. MLB enrichment must therefore come from additional verified provider endpoints and/or external structured sources. Historical raw evidence should be preferred over spending new provider requests when the question can already be answered from archived payloads.


## 76. One-shot live games API audit deployed — 2026-09-26

A direct live API-Sports request could not be issued through the Railway agent because Railway intentionally hides secret variable values from the agent. To execute the user's requested live provider check without exposing the API key, PR #23 added an idempotent one-shot diagnostic to the existing Baseball worker.

Safety properties:

- endpoint: `/games?date=2026-09-26`;
- provider budget hard-capped to exactly 1 request;
- retry attempts hard-capped to 1;
- raw response archived through the existing remote archive;
- audit ID: `games-schema-live-20260926-1`;
- repeat cron executions query `runtime_cycles` and return `ALREADY_DONE` after the first completed audit instead of calling the provider again;
- `BASEBALL_ENABLE_COLLECTION=false`;
- `BASEBALL_ENABLE_CANARY=false`;
- `PAPER_MODE=true`;
- cron and start command unchanged;
- Football untouched.

PR #23 passed Baseball tests and Railway runtime smoke, then was squash-merged to main as `1dca14ebb89292a21a9af359e4d78bed6ceb1408`.

Railway deployment `3f21aaa4-2574-408e-b5d3-b5f8c1cb9fdd` reached SUCCESS at approximately `2026-09-26T00:45:41Z`. Because deployment completion occurred after the 00:45 UTC cron boundary, the live provider request is pending the next natural `*/15` execution. No provider request is claimed yet.


## 77. Live one-request /games audit completed — 2026-09-26

The idempotent one-shot live API-Sports Baseball audit completed successfully on the first natural worker execution after deployment.

Audit evidence:

- audit id: `games-schema-live-20260926-1`;
- endpoint/date: `/games?date=2026-09-26`;
- provider HTTP requests: exactly `1`;
- results: `35` games;
- raw payload archived remotely with checksum `7c5d5476c673feeb1feec7314352ffc8d74cfc0f42b3ccff74d9bb0e931ef448`;
- collection remained disabled;
- canary remained disabled;
- paper mode remained enabled.

League counts in the single live response:

- MLB (id 1): 16;
- NPB (id 2): 5;
- Asian Games (id 32): 4;
- CPBL (id 29): 3;
- KBO (id 5): 3;
- Elitserien (id 27): 2;
- Bundesliga (id 16): 1;
- Division 1 (id 13): 1.

Exact game-record schema observed in MLB and sampled non-MLB rows was the same:

- top level: `country,date,id,league,scores,status,teams,time,timestamp,timezone,week`;
- league: `id,logo,name,season,type`;
- country: `code,flag,id,name`;
- teams: `home,away`;
- each team: `id,logo,name`;
- status: `long,short`;
- scores: `home,away`.

No fields were present in this live `/games` response for injuries, probable/confirmed pitchers, lineups, player statistics, venue/stadium metadata, roof, umpire, or weather. This held for the MLB sample and sampled non-MLB leagues.

A second natural cron run returned `ALREADY_DONE` with `provider_requests=0`, confirming the audit was idempotent and did not repeat the provider call.

Audit control variables were then cleared without a deploy. Collection and canary remain disabled and paper mode remains true.

Interpretation: `/games` is a schedule/status/result spine across leagues. Rich MLB research inputs must come from additional verified endpoints and external structured sources; this result says nothing about the richness of `teams/statistics`, `players/statistics`, `standings`, `odds`, or other provider surfaces.


## 78. Live provider surface audit and bookmaker/market policy evidence — 2026-09-26

Bounded live audit `provider-surface-live-20260926-1` completed on deployment `e3f3dd80-f314-407b-be9a-298c39a22a53` using 9 provider requests against a hard cap of 12. Scheduled collection and canary remained disabled and paper mode remained true.

Verified live findings:

- MLB `standings`: one response group containing 60 team rows;
- NPB `standings`: one response group containing 12 team rows;
- standings row evidence includes team/league/country identity, position, games played, wins/losses with percentages, points/runs for and against, group and stage;
- `odds/bets`: 83 market definitions; first canonical entry was id 1 `Home/Away`;
- `odds/bookmakers`: 30 bookmaker definitions; live sample confirmed bookmaker id 1 `1xbet`;
- `/players?search=ohtani` returned provider error `This endpoint do not exist.`; this path is not to be retried without new documentation/live evidence;
- `teams/statistics` rejects the old `id+season` parameter shape and explicitly requires `league` and `team`;
- `team+league+season` reached a provider response, but that endpoint returns an object while the generic API client currently expects a list. The raw response was archived before the client rejected the response shape.

User execution policy is now explicit: **only Bet365 and 1xBet are playable**. Other bookmaker observations may remain market-intelligence evidence but may never be substituted as the executable paper-pick entry/closing bookmaker. Player-prop markets remain excluded from the product.

API-burn decision: do not re-fetch the already archived `teams/statistics`, `odds/bets` or `odds/bookmakers` payloads merely to inspect their schema. PR #25 introduced a zero-provider-request S3 archive inventory for that purpose and merged as `a74bca8687c6c3346a7872be0c60f9e4b811fb00`.

At the first natural cron after that deployment, the worker exited before inventory execution because cleanup had set `BASEBALL_PROVIDER_SURFACE_AUDIT_SEASON` to an empty string and the worker parsed it with `int("")`. No provider request was made by that failed runtime. Production variables were immediately restored to a safe state with the provider-surface audit ID empty, season `2026`, collection false, canary false and paper mode true. A code hardening patch is being carried in the provider-variable-policy branch so empty optional audit variables cannot crash the worker again.


## 79. Zero-request provider inventory and playable-book policy merged — 2026-09-26

The archive-only provider inventory completed from the existing S3 raw payloads with **provider_requests=0**. It recovered the exact object-shaped `teams/statistics` schemas already paid for during the prior bounded live audit and re-used the archived odds market/bookmaker catalogs instead of re-fetching them.

Verified `teams/statistics` structure for both tested MLB and NPB teams includes home/away/all games played, wins, losses (provider spelling `loses`), win/loss percentages, runs scored totals/averages and runs allowed totals/averages. No additional provider calls were required.

The archived bookmaker catalog confirmed canonical provider ids:

- `1 = 1xbet`;
- `2 = Bet365`.

The archived bet catalog contains 83 definitions. Product scope remains full-game `Home/Away` moneyline first and full-game `Over/Under` next. Player props and inning-specific markets are retained only in immutable raw evidence and excluded from the compact game-level market path.

PR #28 passed the full Baseball test suite and Railway runtime smoke, then squash-merged to main as `7669e99d6ce6f5e815c604b22c9bcf91f84e0738`.

PR #28 enforcement:

- Bet365 and 1xBet are the only playable bookmakers;
- non-playable bookmakers may remain market-intelligence evidence but cannot be selected as a candidate/paper pick;
- `RegisteredPick` fails closed for any bookmaker other than Bet365/1xBet;
- compact odds processing retains approved game-level markets only and excludes player props / inning variants;
- `docs/BASEBALL_VARIABLE_MARKET_REGISTRY.md` is now the canonical variable/market/source/API-refresh registry;
- `docs/BASEBALL_RESEARCH_FEATURE_REGISTRY.md` now points to the canonical live registry and no longer treats player endpoints as verified.

Railway worker deployment for this merge: `cef7b611-0c6f-4c7c-8702-26dbf06d61d1`; at the time of this log it had entered the deployment queue. Safety state remains collection OFF, canary OFF, paper mode ON.


## 80. Production Baseball operations dashboard online — 2026-09-26

A dedicated read-only Railway service, `quantbet-baseball-dashboard` (service id `3c73f36a-7ab3-479b-9726-c26a81996728`), is now online in the guarded Baseball project/environment.

Public domain:

- `https://quantbet-baseball-dashboard-production.up.railway.app`

Dashboard design/behavior:

- separate continuously running service from the cron worker;
- PostgreSQL read-only control plane;
- System / Research / History views;
- evidence-driven green / amber / red / locked states;
- worker freshness, database, API credential configuration, raw archive, migrations, paper mode, collection lock, canary state, fixture freshness and odds freshness;
- API budget/headroom and latest bounded canary evidence;
- lifecycle counts from fixture evidence through predictions, verification, registration, monitoring, closing, settlement and CLV;
- research performance projections and immutable pick history;
- only Bet365 and 1xBet shown as executable bookmakers;
- no fake/demo picks or probabilities;
- no API-Sports client or API_BASEBALL_KEY on the dashboard service;
- dashboard refreshes do not consume provider requests.

Implementation milestones:

- PR #29 merged as `0ccbe2912f581b97629abf97b9dbe3118ac86810` and introduced the dashboard, entrypoint, tests and dashboard contract;
- PR #30 merged as `7c19d2c3d30546ce3543de28210260d9388fd901` and added the root Railpack discovery entrypoint required by Railpack 0.40.0;
- PR #31 merged as `bf51a56f95b168b7d64d1228dff3065930dc293e` and strengthened `/readyz` plus startup to require the complete dashboard snapshot, not merely `SELECT 1`;
- that stronger readiness correctly exposed a dashboard-only psycopg row-factory integration bug: `PostgreSQLEvidenceRepository.health_snapshot()` expects tuple rows while the dashboard had attached `dict_row` to the same connection;
- PR #32 fixed the boundary by using a normal tuple connection for the shared evidence repository and a separate `dict_row` connection for dashboard-specific queries; it merged as `dbf916faaea4e7d6761d5bdbf7eafae91aec245e`.

Final production evidence:

- dashboard deployment `a5aed490-7fba-4057-8ea1-22b2394f0e94` reached SUCCESS;
- Railway full healthcheck on `/readyz` succeeded on the first attempt after the row-factory fix;
- because `/readyz` now executes the complete dashboard snapshot, SUCCESS proves the current production System/Research/History query set is readable against PostgreSQL;
- worker deployment `af32f80a-3c57-4985-ba09-925bb1c0eeb7` also reached SUCCESS on the same main commit;
- worker start command remains `PYTHONPATH=src python -m quantbot.baseball.worker`;
- worker cron remains `*/15 * * * *`;
- worker restart policy remains NEVER;
- scheduled collection remains disabled;
- canary remains disabled;
- paper mode remains enabled;
- Football repo remained read-only.

The previous dashboard deployment failure under PR #31 is intentionally preserved as evidence: full-readiness prevented a false-green dashboard and forced the production SQL integration issue to be corrected before acceptance.


## 81. Market acceptance canary PASSED — 2026-09-26

Natural cron execution at 2026-09-26 06:31 UTC ran the armed bounded acceptance canary on the guarded Baseball production worker.

Canary id: `5dbf934c-c5c6-565f-8425-f49b79964286`  
Cycle id: `3b532cb1-70a0-4159-9839-fa2e8a4697c6`

Acceptance evidence:

- status: **PASSED**;
- provider requests: **6 / 8**;
- broad odds calls: **4**;
- games seen: **65**;
- pregame games: **41**;
- games selected: **4**;
- non-empty odds calls: **3**;
- empty odds calls: **1**;
- raw market rows observed: **522**;
- canonical moneyline rows: **42**;
- PostgreSQL odds observations inserted: **42**;
- fixture observations inserted: **65**;
- bookmaker records inspected by diagnostic probe: **21**;
- collection errors: **0**;
- raw archive verified: **true**;
- PostgreSQL writes verified: **true**;
- canary reason codes: **none**.

Live schema evidence included exact `Home/Away` with Home/Away selections and also confirmed that `Match Winner` can contain Home/Draw/Away. The parser therefore correctly recognizes the two-way market while fail-closing the three-way semantic.

Post-canary health:

- bookmakers: **7**;
- distinct quote games: **3**;
- odds observations: **42**;
- latest odds observed at: `2026-09-26T06:31:10.738698+00:00`.

Scheduled-collection activation assessment immediately after the canary:

- target: `SCHEDULED_COLLECTION`;
- verdict: **READY**;
- api key configured: true;
- canary passed: true;
- collection enabled: false;
- migrations current: true;
- paper mode: true;
- raw archive configured: true;
- runtime fresh: true;
- reason codes: none.

The next natural cron at 06:45 UTC returned `ALREADY_PASSED` for the same canary id and made no second canary ingestion run. Canary was then explicitly disarmed. Collection remains OFF and paper mode remains ON until the fixed 300 RSD stake migration and final downstream readiness checks are completed.


## 82. Fixed 300 RSD paper stake deployed — 2026-09-26

PR #35 passed Baseball tests and Railway runtime smoke and squash-merged to main as `8eb5dc638f95a43ac14d1d893a72e09d98bc0cab`.

Production worker deployment `7ea4ea81-e3d6-4425-9ec9-c47ccb7b37d4` applied migration `008_paper_stake_rsd.sql` through the existing Railway predeploy migration command and reached SUCCESS.

Migration 008 makes paper stake evidence canonical:

- `registered_picks.paper_stake_minor = 30000`;
- `registered_picks.currency = RSD`;
- DB constraints reject arbitrary stake/currency values;
- domain-level `RegisteredPick` independently enforces the same 300 RSD / RSD contract;
- settlement projection exposes `paper_profit_minor`;
- dashboard projection exposes `settled_stake_minor` and `realized_profit_minor`;
- the production Baseball dashboard now reads DB-backed monetary P/L rather than deriving monetary stake only in the frontend.

The first dashboard deploy raced ahead of the worker migration and correctly failed full-readiness on missing `settled_stake_minor`. After migration 008 was applied, dashboard redeploy `4ba844a2-0eec-461b-a210-086b8c544efe` reached SUCCESS with the same full-snapshot readiness gate. This is preserved as positive fail-closed migration-order evidence.

Worker safety remains PAPER_MODE=true, canary=false and collection=false at this checkpoint.


## 2026-09-26 post-activation live read-back and API-burn diagnosis

This entry records a fresh read-only production verification after scheduled collection activation.

Authoritative live evidence:

- GitHub default branch remains `main` at `8eb5dc638f95a43ac14d1d893a72e09d98bc0cab`;
- PR #34 is merged as `35f76de13ee42e4d93df4a8334e4bb1faba92b0d`;
- PR #35 is merged as `8eb5dc638f95a43ac14d1d893a72e09d98bc0cab`;
- PR #13 remains open and intentionally unmerged;
- guarded Railway target is still project `believable-contentment`, production environment `32ceeb6e-a8a8-4f98-b757-58d63417e496`;
- worker `quantbet-baseball` latest deployment `cce8c01e-013e-4f53-87fe-5c2414b1f36a` is SUCCESS on main `8eb5dc6`;
- dashboard latest deployment `4ba844a2-0eec-461b-a210-086b8c544efe` is SUCCESS on the same main commit;
- dashboard Railway healthcheck step completed successfully with configured path `/readyz`; public root requests observed by Railway returned HTTP 200;
- migration 008 is proven applied by pre-deploy output `('008_paper_stake_rsd.sql',)`; the subsequent redeploy reports no pending migrations;
- immediately pre-activation activation-gate evidence reported `paper_mode=true`, `canary_passed=true`, `migrations_current=true`, raw archive configured, and no blocker codes;
- current worker runtime evidence reports `collection_enabled=true` and `canary_enabled=false`.

First observed scheduled collection cycle after activation:

- cycle `ecd78577-abb1-4d08-b740-24bcb33411d0`;
- execution mode `SCHEDULED`;
- 56 / 75 API requests used;
- 54 broad odds calls;
- 65 games seen, 54 pregame games, 54 games selected;
- 2,757 compact raw market rows;
- 190 canonical moneyline rows inserted;
- zero collector/provider errors;
- durable health after the cycle: 96 distinct fixtures, 390 fixture observations, 232 odds observations, 15 distinct quote games, 7 bookmakers, and zero model predictions/value evaluations/registered picks/settled picks.

### API-burn root cause found

Code review of `src/quantbot/baseball/durable_collector.py` found a deterministic scheduler bypass. The collector correctly builds a `due` list using `is_observation_due(...)`, but selection then iterates over `(due, learning)`. The `learning` list contains every eligible pregame game inside 36 hours, so unused request capacity is filled with games that are explicitly not due. With 54 eligible games and a broad-odds cap above that count, all 54 games are polled on every 15-minute cron regardless of the intended 120/60/30/15-minute adaptive cadence.

This explains the observed 54 odds calls in one cycle and is a real API-efficiency defect, not a tuning preference.

Immediate engineering action: preserve collection activation, fix scheduled selection so non-due games cannot consume broad discovery capacity, add regression coverage and explicit efficiency telemetry, and validate the change before production merge. Do not lower the global budget/cap as a substitute for correcting scheduling semantics.


## 2026-09-26 adaptive odds cadence repair merged and deployed

Additional production evidence made the API-burn defect measurable before the repair deployed.

Old-code scheduled cycle at `2026-09-26T07:31:42Z`:

- cycle: `00305c67-5422-4206-9e21-484a0a4078d1`;
- provider requests: 57 / 75;
- games seen: 65;
- pregame games: 55;
- scheduler due events: **45**;
- games selected for odds: **55**;
- odds calls: **55**;
- raw compact market rows: 2,757;
- canonical rows / observations inserted: 190 / 190;
- errors: 0.

Therefore at least **10 broad odds requests in that single cycle were explicitly non-due** according to the project's own adaptive cadence. This directly confirms the due+learning fallback was consuming quota outside scheduler intent.

Repair PR #38, `Honor adaptive cadence for scheduled odds polling`, changed broad selection to consume only `due` games. It also adds `not_due_events` and `due_events_unselected` telemetry and a regression test proving a recently observed game is not queried before its interval expires.

Validation:

- Baseball tests: PASS;
- Railway runtime smoke: PASS;
- PR #38 squash-merged to main as `a6dd7624040249b233453272f25029ef92446815`;
- worker deployment `885575ba-0750-4b61-87fb-08cf5a096a57`: SUCCESS;
- dashboard deployment `12008f77-e4ec-46ac-a05a-eaff68faab83`: SUCCESS;
- collection was not disabled;
- cron, request budget, bookmaker policy, paper mode and Football resources were not changed.

Acceptance of the burn repair still requires a natural scheduled production cycle on `a6dd762...` proving `games_selected <= due_events` and exposing the new telemetry. No API-saving claim beyond the demonstrated old-code waste is considered complete until that live post-deploy evidence exists.


## 2026-09-26 post-repair production cycle and second API-burn defect

The first natural scheduled collection observed after the adaptive due-only repair ran on main `7af3f59c318a9724c60a5af0b9d3a0b02ca26675` through worker deployment `b045c5e1-e0cb-4a7a-b1bc-f3d4edc708cf` (SUCCESS).

Cycle `ee7e84d4-92d6-4017-b75d-e62035626444` at ~07:46 UTC:

- execution mode: SCHEDULED;
- API requests: 42 / 75;
- games seen: 65;
- pregame games: 55;
- due events: 40;
- not-due events: 15;
- games selected: 40;
- due events unselected: 0;
- odds calls: 40;
- raw market rows: 0;
- canonical rows: 0;
- observations inserted: 0;
- errors: 0.

This is production proof that PR #38 repaired the first scheduler bypass: `games_selected == due_events`, and 15 explicitly non-due games did not consume broad odds calls. Compared with the pre-fix cycle where 45 due became 55 selected, broad selection now honors the scheduler.

However, the same cycle exposed a second burn defect: all 40 successful odds calls returned empty provider responses. The scheduler's prior timestamp is currently derived only from `odds_observations`. An empty but successful archived odds response creates no canonical quote row, therefore no latest observation timestamp. Such games can remain due on every 15-minute cron even though they were just checked.

Required repair: persist a durable per-game odds poll-attempt fact for every successful provider odds response, including empty responses and the raw archive receipt/checksum. Adaptive scheduling must use the latest successful poll attempt, not only the latest parsed quote observation. Provider errors must remain distinguishable from successful empty responses.

### Dashboard API-efficiency telemetry

PR #40, `Show scheduled collection efficiency on dashboard`, passed Baseball tests and was squash-merged as `7af3f59c318a9724c60a5af0b9d3a0b02ca26675`.

Dashboard deployment `8e2dc6bc-3c54-4efb-b786-3e4446a2184e` is SUCCESS. The System view now exposes persisted latest-cycle requests/cap, due games, selected games, not-due games, odds calls and canonical observations per provider request. The dashboard remains read-only and makes no provider calls.

### Official MLB structured-source live audit

Draft PR #39 is audit-only and must not be merged. Its bounded public no-auth MLB Stats API audit passed on commit `f9ab46d3d674001db7a32072a2b5151e3716a146`: 135 tests passed, 6 skipped.

Verified live on 2026-09-26:

- `/api/v1/schedule?sportId=1&date=2026-09-26&hydrate=probablePitcher,team,venue` returned 13 MLB games and structured probable-pitcher/team/venue data;
- first sampled game `gamePk=822678` exposed Mets probable starter Jonah Tong (MLB id 804636), Nationals probable starter Connelly Early (MLB id 813349), and Nationals Park (venue id 3309);
- `/api/v1.1/game/822678/feed/live` exposed `gameData.probablePitchers`, `gameData.players`, venue/location/time-zone/field metadata, and boxscore team structures including battingOrder, bullpen, pitchers and players;
- the sampled early-pregame feed had an empty `gameData.weather` object, which is treated as absent evidence, never as zero values;
- active roster query returned 28 rows with person/position/status identity fields;
- transactions query for 2026-09-24 through 2026-09-26 returned 67 rows with date/effectiveDate/person/team/type/description fields.

Lineup-capable schema is verified, but confirmed-lineup availability is not yet proven for an actual populated pregame snapshot. Expected and confirmed lineup states remain separate by contract. Historical `timecode` replay is the next bounded audit before point-in-time ingestion is approved.


## 2026-09-26 successful-empty-poll cadence evidence and MLB replay verification

### API-burn repair #2

PR #41, `Persist successful empty odds polls for cadence`, passed both Baseball tests and Railway runtime smoke and was squash-merged as `527790c13a76811c7c63300b5504dcf0f7a495e4`.

Migration `009_odds_poll_attempts.sql` adds immutable evidence for every successful API-Sports game-odds response, including empty responses. Each record preserves game/provider identity, actual capture time, kickoff, response/raw/canonical row counts and the raw archive ref/checksum. Scheduler cadence now keys off latest successful odds poll attempt rather than only parsed quote observations. A provider error does not create successful poll evidence.

Worker deployment `008ce875-1c54-47aa-98aa-77eab7bf5bfc` is SUCCESS. Predeploy evidence at 07:55:45 UTC confirms:

`{'migrations_applied': ('009_odds_poll_attempts.sql',)}`

This fixes the second burn defect discovered by cycle `ee7e84d4-92d6-4017-b75d-e62035626444`, where 40/40 due odds requests were successful but returned zero market rows; before migration 009 such empty calls had no durable last-check timestamp and could become due again every cron.

A natural post-migration cycle is still required to prove the new empty-response throttle in production across consecutive cron runs.

### Dashboard deployment race observed and resolved

The first dashboard deploy of `527790c...` failed readiness because it started before worker predeploy had created `odds_poll_attempts`; readiness correctly failed with PostgreSQL `UndefinedTable` rather than reporting a false green state. After migration 009 applied, dashboard-only redeploy `3ebfcb50-5594-4f6b-99b9-aeec2a9635d1` succeeded without code/schema changes. This was a deployment-order race, not a dashboard query defect.

### Official MLB historical replay verified

Audit-only PR #39 was never merged and has now been closed after evidence was harvested into canonical docs.

Bounded official MLB Stats API audit passed with 136 tests / 6 skipped. Historical `timecode` replay on completed game `823570` requested `20260920_151000` for a game scheduled at `2026-09-20T17:10:00Z` and returned:

- `Pre-Game` status;
- probable pitchers for both sides;
- populated 9-player batting orders for both teams;
- 28 player records per team in the sampled boxscore state;
- bullpen/pitcher identity arrays;
- response `metaData.timeStamp=20260920_151258`.

The 2m58s difference between requested timecode and response metadata timestamp is a critical anti-leakage finding. Historical feature ingestion must use the actual provider response metadata timestamp as source cutoff evidence. A requested timestamp alone is insufficient.

PR #42, `Document verified official MLB source contracts`, passed tests and was squash-merged as `74eeb9cf3220225143c780425269860c2d711c31`. The canonical variable and research feature registries now record these source contracts, current scheduled-collection state and migration-009 empty-poll semantics.
