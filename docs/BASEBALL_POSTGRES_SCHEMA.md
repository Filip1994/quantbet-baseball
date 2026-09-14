# QuantBet Baseball — PostgreSQL Schema Foundation

**Status:** schema foundation; not yet connected to Railway.

## Purpose

This migration establishes the durable relational boundary for canonical odds observations and immutable pick events. It deliberately does not implement provider ingestion, settlement, archival, retention deletion, or deployment configuration.

## Tables

### `odds_observations`

Stores one canonical, timestamped market observation. `observation_id` is immutable and unique. The canonical record is retained as `JSONB` to preserve the validated envelope while relational columns support constraints and indexed retrieval.

Important protections:

- decimal odds must be greater than 1;
- `retrieved_at` cannot precede `observed_at`;
- supported market families are currently `moneyline` and `full_game_total`;
- market status is explicit;
- source payload checksum must be a 64-character hexadecimal SHA-256 value;
- canonical record must be a JSON object;
- primary-key collisions must be handled by the repository adapter as either an exact idempotent duplicate or a fail-closed conflict.

### `pick_events`

Stores immutable `BET` and `PASS` decisions. The table retains decision context, model and feature references, market snapshot reference, source-data cutoff, and canonical record.

`PASS` events intentionally require all numerical pricing and value metrics to be null. This prevents a later consumer from treating a non-bet as an executable priced position.

## Adapter obligations

The future PostgreSQL repository must:

1. validate records through the Python canonical contracts before insertion;
2. use parameterized SQL only;
3. perform inserts transactionally;
4. treat exact duplicate immutable IDs as idempotent;
5. reject conflicting duplicate IDs without overwrite;
6. preserve canonical payloads losslessly;
7. expose deterministic ordering for reads;
8. provide schema/version visibility;
9. never silently update an existing evidence row;
10. support replay-safe retries.

## Lifecycle boundary

The database is the active evidence store. Raw provider payloads and high-volume intermediate artifacts may later be exported to verified cold storage, but no retention or deletion policy is implemented by this migration. Pick events, settlement evidence, CLV, model metadata, and audit lineage must remain recoverable.

## Deployment status

This is a repository migration artifact only. It has **not** been applied to Railway, and no runtime database test has been claimed.
