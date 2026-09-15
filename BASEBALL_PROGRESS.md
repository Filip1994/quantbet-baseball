

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
