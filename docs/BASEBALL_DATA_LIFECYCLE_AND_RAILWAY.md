# QuantBet Baseball — Data Lifecycle and Railway Architecture

**Created at:** 2026-09-15  
**Last updated:** 2026-09-15  
**Revision:** 1.1  
**Status:** ARCHITECTURAL BASELINE — implementation pending

## 1. Decision

Railway is the explicit operational control plane for QuantBet Baseball.

The intended separation is:

- **GitHub:** source code, version control, review, CI, and auditable change history;
- **Railway:** application startup, scheduled execution, workers, runtime configuration, secrets, observability, and operational persistence;
- **PostgreSQL on Railway:** canonical transactional memory for evidence and evaluation data;
- **External cold archive:** verified long-term exports only, not the active system of record.

GitHub Actions may remain useful for CI and repository validation, but it is not the intended production execution engine for ingestion, decisioning, settlement, or evaluation.

The system must not be considered operational merely because source code exists in GitHub. Railway must run the actual processes that produce and preserve the evidence lifecycle.

## 2. Minimal target architecture

```text
GitHub repository
├── source code
├── tests
├── migrations
├── CI validation
└── versioned configuration

Railway project
├── PostgreSQL
│   ├── canonical market observations
│   ├── immutable pick events
│   ├── market snapshots and timeline metadata
│   ├── settlement and CLV records
│   └── audit and schema metadata
├── ingestion worker
├── evaluation/settlement worker
├── API or control/health service
└── scheduled archive/maintenance job

External cold archive
└── verified exports and historical raw payload archives
```

The architecture must remain vertically coherent: ingestion, evidence, decisions, settlement, evaluation, and archival must share explicit contracts and timestamps.

## 3. Runtime ownership rules

1. Every production process must have an explicit Railway service or process definition.
2. Every process must have a documented entrypoint and bounded failure behavior.
3. Runtime secrets and provider credentials must be configured in Railway, never committed to GitHub.
4. PostgreSQL migrations must be versioned in GitHub and applied deliberately to the Railway database.
5. Runtime writes must target the Railway PostgreSQL evidence store, not generated files committed back to GitHub.
6. GitHub Actions must not be treated as the source of truth for production state.
7. A deployment is not accepted until startup, health, persistence, and restart behavior are verified.

## 4. Data classes

### Hot operational data

Remain queryable in Railway PostgreSQL:

- immutable pick events;
- settlement results;
- CLV and closing-price measurements;
- model and feature version metadata;
- audit records;
- active and recently used odds timelines;
- data required for current validation and replay.

### Warm data

May remain in PostgreSQL while actively used, then be archived:

- older detailed odds observations;
- historical market snapshots;
- normalized provider records;
- intermediate evaluation artifacts.

### Cold archive

May be exported to compressed files such as Parquet or compressed JSONL:

- immutable raw provider payloads;
- old detailed odds observations;
- historical snapshots and intermediate artifacts;
- export manifests and checksums.

Pick events, settlement, CLV, model-version metadata, and audit lineage should not be removed merely because their underlying raw payloads are old. They are the compact evidence trail of the system.

## 5. Retention and deletion rules

No automatic deletion is permitted until all of the following exist:

1. a documented retention class;
2. a deterministic export format;
3. an export manifest;
4. a checksum for every archive object;
5. a successful read-back verification;
6. a tested restore/import procedure;
7. an explicit retention policy approved in project documentation.

Age alone is not a sufficient deletion criterion. Data must also be checked for active references from replay, audit, model validation, settlement, or research jobs.

## 6. Backup policy

The monthly cold archive is a long-term archive, not the only backup.

The operational system should additionally support:

- automated PostgreSQL backups or logical dumps;
- a recovery point objective appropriate to ingestion volume;
- periodic restore tests;
- archive manifests containing schema version, export timestamp, record counts, and checksums;
- protection against deleting active data before archive verification.

The first implementation may keep the policy simple, but it must fail closed rather than silently discard data.

## 7. Storage and scale principles

Railway hosting capacity does not remove database engineering requirements. Before large-scale ingestion, the system must account for:

- indexes aligned with time-range and game/market queries;
- partitioning when measured volume justifies it;
- compression and export formats;
- idempotent ingestion;
- duplicate and conflict detection;
- query limits and bounded batch sizes;
- backup and restore duration;
- storage, compute, and network cost.

The system must distinguish storage capacity from RAM. Terabyte-scale retention is a storage and data-layout problem; individual queries must still be bounded and efficient.

## 8. Implementation order

1. Stabilize database-neutral evidence repository contracts.
2. Implement PostgreSQL schema and migrations.
3. Implement transactional append-only persistence.
4. Define the first real Railway runtime entrypoint.
5. Connect runtime configuration and secrets through Railway.
6. Connect ingestion and evaluation workers to PostgreSQL.
7. Add deterministic reads, health checks, and failure reporting.
8. Add archive export manifests and checksum verification.
9. Add retention eligibility checks.
10. Add deletion only after restore and replay tests exist.

SQLite is not part of the intended production architecture unless a future explicit decision changes this baseline.
