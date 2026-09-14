

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
