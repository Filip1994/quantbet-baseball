# QuantBet Baseball — Repository Contract

**Created at:** 2026-09-15 Europe/Belgrade  
**Last updated:** 2026-09-15 Europe/Belgrade  
**Revision:** 1.0  
**Status:** DESIGN BASELINE — contract defined; concrete durable adapter not yet implemented

## Purpose

This document defines the storage boundary between baseball evidence logic and
its persistence implementation. The application must not depend directly on
SQLite, PostgreSQL, Railway, or a filesystem when expressing evidence
semantics.

## Canonical contract

The repository exposes append-only operations for:

- `OddsObservation` records;
- `PickEvent` records.

It also exposes deterministic point lookups, ordered reads, and basic counts.

## Required adapter behavior

Every adapter must preserve the following rules:

1. **Immutable identity** — `observation_id` and `pick_id` are stable primary identities.
2. **Idempotency** — replaying an identical record is a no-op and returns `False`.
3. **Conflict rejection** — reusing an identity with different canonical content fails closed.
4. **No silent overwrite** — an existing record may never be replaced implicitly.
5. **Canonical equality** — duplicate comparison uses the canonical serialized record.
6. **Deterministic reads** — result ordering is explicit and stable.
7. **Schema visibility** — persisted records retain their evidence `schema_version`.
8. **Atomicity** — a batch append either satisfies the adapter's documented transaction boundary or fails without a partial, silent commit.
9. **Replay safety** — ingestion and replay must be able to retry without creating divergent evidence.
10. **Auditability** — persistence errors and conflicts must be observable to the caller and operational logs.

## Railway/PostgreSQL direction

The intended production adapter is PostgreSQL hosted on Railway. This is an
implementation choice, not part of the domain contract. SQLite is not a
production target for this project.

The future adapter must support:

- transactional inserts;
- unique constraints on immutable IDs;
- canonical payload storage or an equivalent lossless representation;
- deterministic indexes for game, market, timestamp, and identity access;
- migration/version control;
- explicit conflict handling;
- later archival without deleting the compact pick/settlement/audit trail.

## Deliberate non-goals

This contract does not yet define:

- settlement tables;
- archive export jobs;
- retention deletion;
- provider-specific ingestion;
- Railway deployment configuration;
- automated staking.

Those are subsequent vertical slices and must not bypass this boundary.
