# QuantBet Baseball — Package D Worklog

**Date:** 2026-09-25  
**Branch:** `finish/settlement-clv-dashboard-20260925`  
**Repository:** `Filip1994/quantbet-baseball`  
**Railway project:** `believable-contentment`  
**Production service:** `quantbet-baseball`

## Guardrails

- Baseball only.
- Football repository `Filip1994/v2quantbet` is reference-only and was not modified.
- Football Railway project was not touched.
- Production collection remains disabled.
- Paper mode only.
- No staking or real-money execution.

## Package C production verification

Before starting Package D, Railway production state was checked.

Verified:

- deployment `1cc8cd65-238e-4c50-986c-9882ab39e281` is `SUCCESS`;
- deployment commit is `8bb4aed32b66dc044436c2e2c28d8dadab848483`;
- deploy log explicitly contains:
  - `{'migrations_applied': ('005_moneyline_monitoring_closing.sql',)}`;
- later cron runs show:
  - `collection_enabled=false`;
  - `mode=storage-ready`;
  - `status=ready`.

Conclusion:

> Package C is deployed and migration 005 is verified in Baseball production.

## Package D objective

Close the moneyline lifecycle after immutable closing:

```text
registered pick
→ closing finalization
→ authoritative result evidence
→ deterministic settlement
→ realized CLV
→ operational projection
→ dashboard projection
```

The implementation must remain point-in-time auditable and fail closed when closing evidence is incomplete.

## Schema added

Created `migrations/006_moneyline_settlement_clv.sql`.

### game_result_facts

Purpose:

- append-only provider-sourced terminal result evidence;
- retains fixture observation provenance;
- retains final scores;
- derives explicit winner;
- preserves raw payload pointer/checksum;
- stores canonical JSON.

Key invariants:

- non-negative scores;
- winner must match score;
- immutable trigger;
- result references a concrete fixture observation.

### pick_settlements

Purpose:

- one immutable settlement per registered pick;
- explicit result and closing provenance;
- realized profit per unit;
- CLV result only when closing evidence is CAPTURED.

Settlement outcomes:

- `WIN`;
- `LOSS`;
- `PUSH`.

CLV states:

- `AVAILABLE`;
- `UNAVAILABLE_STALE_QUOTE`;
- `UNAVAILABLE_NO_VALID_QUOTE`.

No missing close is converted into a numerical CLV.

### Read models

Created:

- `baseball_moneyline_pick_projection`;
- `baseball_moneyline_dashboard`.

The dashboard is projection-only. It does not mutate lifecycle facts.

Projected metrics include:

- registered picks;
- closing finalizations;
- settled picks;
- pending settlement;
- wins;
- losses;
- pushes;
- realized profit per unit;
- CLV available / unavailable counts;
- average probability CLV;
- average price-ratio CLV.

## Domain implementation

Created `src/quantbot/baseball/settlement_lifecycle.py`.

Implemented:

- `GameResultFact`;
- `PickSettlement`;
- canonical JSON serialization;
- final-result extraction;
- score validation;
- deterministic winner derivation;
- deterministic settlement;
- realized CLV calculation from exact closing quote pair.

CLV definition stored in this package:

- closing two-way moneyline pair is de-vigged;
- selected closing market probability is compared with entry de-vigged market probability;
- `clv_probability_delta = closing_market_probability - entry_market_probability`;
- `clv_price_ratio = entry_odds / closing_odds - 1`.

Positive values mean the registered entry beat the closing market in the selected direction.

## Repository implementation

Created `src/quantbot/baseball/settlement_repository.py`.

Implemented:

- append-only result persistence;
- immutable conflict detection;
- exact closing-pair retrieval;
- due-settlement selection;
- restart-safe settlement replay;
- dashboard snapshot.

## Runtime implementation

Created `src/quantbot/baseball/moneyline_settlement.py`.

For each due closed pick:

1. load pick and latest known fixture;
2. fetch one fresh provider game response;
3. archive provider response through existing raw archive boundary;
4. persist the fresh fixture observation;
5. require terminal provider status plus complete score;
6. persist authoritative result fact;
7. settle the paper pick;
8. compute CLV only if closing outcome was CAPTURED.

Nonterminal games remain unsettled and are eligible for a future refresh.

## Durable collector integration

Updated `src/quantbot/baseball/durable_collector.py`.

New priority order inside a collection cycle:

1. post-game settlement refreshes;
2. active-pick monitoring / closing refreshes;
3. broad pregame market collection.

New bounded setting:

- `BASEBALL_MAX_SETTLEMENT_REFRESHES`, default `10`.

The settlement and monitoring lanes share the same underlying API client/request counter with broad collection.

## Health projection

Updated `src/quantbot/baseball/postgres_repository.py`.

Added health fields:

- `game_result_facts`;
- `settled_picks`;
- `clv_available`.

## Tests added

### tests/test_settlement_lifecycle.py

Covers:

- captured close → CLV available;
- stale close → no fabricated CLV;
- missing valid close → no fabricated CLV;
- WIN / LOSS / PUSH semantics.

### tests/test_moneyline_settlement.py

Covers:

- terminal provider result creates result + settlement;
- nonterminal provider state does not settle.

### tests/test_settlement_postgres_integration.py

Covers full PostgreSQL lifecycle:

```text
fixture
→ odds
→ prediction
→ preliminary evaluation
→ final quote verification
→ registered pick
→ monitoring
→ captured close
→ final result fixture
→ authoritative game_result_fact
→ pick_settlement
→ CLV
→ dashboard
→ health
→ replay
```

## CI integration

Updated `.github/workflows/railway-runtime-smoke.yml` so Package D source and tests participate in:

- path triggering;
- Ruff format check;
- Ruff lint;
- focused pytest;
- PostgreSQL integration execution.

## Current status

Implementation is present on the Package D branch.

Still required before completion:

- inspect final diff;
- observe CI;
- fix failures if any;
- document fixes here and in `BASEBALL_PROGRESS.md`;
- merge;
- verify Railway deploy;
- verify migration `006_moneyline_settlement_clv.sql` in runtime logs.

Production collection remains OFF throughout this package unless a separate explicit activation decision is made.
