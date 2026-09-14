# QuantBet Baseball — Odds Timeline and Pick Event Specification

**Repository:** `Filip1994/quantbet-baseball`  
**Created at:** 2026-09-15 01:00 Europe/Belgrade (UTC+02:00)  
**Last updated:** 2026-09-15 01:00 Europe/Belgrade (UTC+02:00)  
**Revision:** 1.0  
**Status:** DESIGN BASELINE — NOT YET IMPLEMENTED

## 1. Purpose

This document defines the minimum evidence model required before QuantBet Baseball can claim to evaluate a betting edge. A model probability without the exact market price available at the decision timestamp is not an auditable betting signal.

The design separates immutable market observations from immutable decision events and later evaluation records.

## 2. V1 market scope

Included:

- full-game moneyline;
- full-game totals with an explicit line, initially observed lines such as 8.5 and 9.5.

Excluded permanently:

- player props;

Postponed:

- run line;
- F5 markets;
- team totals;
- NRFI/YRFI;
- alternate lines;
- futures;
- parlays and same-game parlays;
- live betting;
- automated staking.

## 3. Immutable market observation

Each observation must contain, at minimum:

- `observation_id` — deterministic or globally unique identifier;
- `game_id`;
- `market_family`;
- `line` — required for totals and other line-based markets, null only where not applicable;
- `selection`;
- `bookmaker` or provider identifier;
- `decimal_odds`;
- `raw_price` and raw selection text where available;
- `observed_at` — provider/source timestamp if available;
- `retrieved_at` — timestamp when QuantBet obtained the payload;
- `source_payload_ref`;
- `source_payload_checksum`;
- `schema_version`;
- `market_status` and suspension state when available.

Rules:

1. All timestamps must be timezone-aware.
2. `retrieved_at` must never be silently substituted for `observed_at`.
3. Missing provider timestamps must be represented explicitly as unknown.
4. Observations after kickoff cannot be used as pre-game evidence.
5. Exact duplicates may be idempotently ignored.
6. Conflicting duplicates must fail closed and remain visible for audit.
7. A market identity includes game, family, line, selection, and bookmaker.

## 4. Immutable pick event

A pick event is created only once, at the time the system makes a decision. It must never be overwritten by later odds or model results.

Required fields:

- `pick_id`;
- `game_id`;
- `market_family`;
- `line`;
- `selection`;
- `decision` (`BET` or `PASS`);
- `decision_reason`;
- `decision_at`;
- `model_version`;
- `feature_snapshot_ref`;
- `market_snapshot_ref`;
- `decision_decimal_odds`;
- `model_probability`;
- `fair_decimal_odds`;
- `market_implied_probability`;
- `edge`;
- `expected_value_per_unit`;
- `uncertainty_metric` and uncertainty approval state;
- `source_data_cutoff_at`;
- `schema_version`.

For a `PASS`, the record must still preserve the evaluated market context and reason. Rejected signals are part of the research sample and must not disappear.

## 5. Timeline semantics

For each game/market/selection, the system should be able to identify:

- first valid pre-game observation: opening proxy;
- latest valid observation before decision: decision price;
- observations after decision and before kickoff;
- first valid post-kickoff observation, which marks the pre-game cutoff;
- final valid pre-kickoff observation: closing proxy;
- stale gaps and missing intervals.

The terms “opening” and “closing” must be qualified as **observed opening** and **observed closing** unless the provider guarantees complete market history.

No interpolation may create a price that was never observed.

## 6. CLV and movement

CLV calculations must specify:

- the exact selection and line;
- the decision price;
- the closing proxy price;
- the odds representation used for comparison;
- whether comparison is made in implied probability, fair probability, or another documented convention.

If the market changes line (for example, total 8.5 to 9.0), it is not the same market observation. It must not be treated as a simple price movement without explicit line-change handling.

Missing closing prices produce `CLV_UNKNOWN`, not zero CLV.

## 7. Settlement record

Settlement must be separate from the pick event and must contain:

- `game_id`;
- exact market family and line;
- selection;
- official result reference;
- settlement status (`WIN`, `LOSS`, `PUSH`, `VOID`, `UNKNOWN`);
- settled_at;
- source reference and checksum;
- settlement rule version.

A pick cannot be scored using an inferred or manually guessed result.

## 8. Replay and audit requirements

A historical decision must be replayable using only evidence available at or before `decision_at`.

The replay contract must reject:

- post-kickoff features;
- future lineup or pitcher information;
- future odds;
- missing market identity;
- timezone-naive timestamps;
- unversioned model or feature definitions;
- conflicting source records.

## 9. Implementation order

1. Define typed observation and pick-event contracts.
2. Add validation and deterministic serialization.
3. Add fixtures for duplicates, conflicts, stale prices, missing timestamps, line changes, and post-kickoff data.
4. Add append-only JSONL or database persistence boundary.
5. Add timeline reconstruction from observations.
6. Add settlement linkage.
7. Add CLV and replay evaluation.
8. Only then connect the decision pipeline.

## 10. Acceptance criteria

This specification is considered implemented only when:

- contracts exist in code;
- invalid records fail closed;
- fixtures cover the listed edge cases;
- records can be serialized and reloaded without semantic loss;
- a pick event references the exact market snapshot used for the decision;
- closing and settlement data remain separate immutable records;
- tests are executed in CI and their result is documented.
