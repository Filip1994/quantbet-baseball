# QuantBet Baseball — Data Lifecycle and Railway Architecture

**Created at:** 2026-09-15  
**Last updated:** 2026-09-15  
**Revision:** 1.0  
**Status:** ARCHITECTURAL BASELINE — implementation pending

## 1. Decision

Railway is the intended operational platform for QuantBet Baseball. The project does not require SQLite as a production persistence layer.

The active system may be composed entirely of services hosted on Railway, with PostgreSQL used as the transactional database and Railway-managed persistent storage used only where file-based storage is appropriate.

A separate cold archive is allowed for long-term retention, but it is not the primary operational datastore.

## 2. Minimal target architecture

```text
Railway project
├── PostgreSQL
│   ├── canonical market observations
│   ├── immutable pick events
│   ├── market snapshots and timeline metadata
│   ├── settlement and CLV records
│   └── audit and schema metadata
├── ingestion worker
├── evaluation/settlement worker
├── API or control service
└── scheduled archive/maintenance job

External cold archive
└── verified monthly exports and historical raw payload archives
```

The architecture must remain vertically coherent: ingestion, evidence, decisions, settlement, evaluation, and archival must share explicit contracts and timestamps.

## 3. Data classes

### Hot operational data

Remain queryable in PostgreSQL:

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

## 4. Retention and deletion rules

No automatic deletion is permitted until all of the following exist:

1. a documented retention class;
2. a deterministic export format;
3. an export manifest;
4. a checksum for every archive object;
5. a successful read-back verification;
6. a tested restore/import procedure;
7. an explicit retention policy approved in project documentation.

Age alone is not a sufficient deletion criterion. Data must also be checked for active references from replay, audit, model validation, settlement, or research jobs.

## 5. Backup policy

The monthly cold archive is a long-term archive, not the only backup.

The operational system should additionally support:

- automated PostgreSQL backups or logical dumps;
- a recovery point objective appropriate to ingestion volume;
- periodic restore tests;
- archive manifests containing schema version, export timestamp, record counts, and checksums;
- protection against deleting active data before archive verification.

The first implementation may keep the policy simple, but it must fail closed rather than silently discard data.

## 6. Storage and scale principles

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

## 7. Implementation order

1. Stabilize database-neutral evidence repository contracts.
2. Implement PostgreSQL schema and migrations.
3. Implement transactional append-only persistence.
4. Add deterministic reads and conflict reporting.
5. Add ingestion and evaluation workers.
6. Add archive export manifests and checksum verification.
7. Add retention eligibility checks.
8. Add deletion only after restore and replay tests exist.

SQLite is not part of the intended production architecture unless a future explicit decision changes this baseline.
