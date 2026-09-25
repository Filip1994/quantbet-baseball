# QuantBet Baseball — Package E Operational Acceptance Worklog

**Date:** 2026-09-25  
**Branch:** `finish/package-e-canary-acceptance-20260925`  
**Repository:** `Filip1994/quantbet-baseball`  
**Railway project:** `believable-contentment`

## Non-negotiable guardrails

- Baseball only.
- Football Railway project is untouched.
- Football repository is untouched.
- Scheduled collection remains disabled.
- Paper mode remains mandatory.
- Canary execution must be bounded and separately identifiable.
- Every activation decision must be reconstructable from durable evidence.

## Package D production closure

Package D was verified before starting this package.

GitHub:

- PR #8 is merged.
- Merge commit: `0f1126fec305de58562c5551b0d81f36df7a2b9a`.
- PR head workflows:
  - Baseball tests: SUCCESS;
  - Railway runtime smoke: SUCCESS.

Railway:

- deployment: `1fc35c1d-9c1c-4843-b52e-154cb60411f9`;
- status: SUCCESS;
- migration log:
  - `006_moneyline_settlement_clv.sql` applied;
- storage-ready cron continues successfully;
- `BASEBALL_ENABLE_COLLECTION` remains effectively false.

## Package E target

Build the explicit boundary between “code is green” and “production collection may be activated”.

Target states:

```text
BLOCKED
→ READY_FOR_CANARY
→ CANARY_PASSED
→ READY_FOR_SCHEDULED_COLLECTION
```

The system must explain every blocked gate with concrete reason codes.

## Existing activation criteria recovered from project docs

Before scheduled collection activation:

1. lifecycle slices are green;
2. exact API budget math including retries is verified;
3. one bounded canary succeeds;
4. DB freshness/coverage is visible;
5. raw archive writes are verified;
6. no identity conflicts occur;
7. downstream paper lifecycle is ready to consume evidence;
8. production remains PAPER_MODE=true.

## Critical budget defect found

The pre-monitoring collector used:

- 2 schedule requests per cron cycle;
- up to 76 odds requests;
- 78 maximum provider attempts per 15-minute cycle;
- 96 cycles/day;
- 78 × 96 = 7,488 attempts/day.

This fit under a 7,500 request/day subscription ceiling with only 12 requests of theoretical headroom.

The closed lifecycle now also has higher-priority provider work:

- settlement refresh:
  - up to one game request per due closed pick;
- monitoring refresh:
  - one game request per due active pick;
  - potentially one odds request per due active pick;
- broad collector:
  - two schedule requests;
  - remaining broad odds requests.

Current code only reduces the broad odds allowance by monitoring odds calls. It does not subtract every settlement/fixture call from the old 76-odds budget.

Therefore the old cap is no longer a valid daily ceiling.

## Required budget design

Package E will replace the effective “odds-only cap” with a shared total fresh-request budget per cron cycle.

Principles:

- settlement gets first priority;
- monitoring gets second priority;
- broad schedule discovery must reserve two calls;
- broad odds collection gets only remaining capacity;
- retries count because `BaseballAPIClient.request_count` increments before every HTTP attempt;
- the acceptance report must expose:
  - cron cycles/day;
  - per-cycle request cap;
  - worst-case attempts/day;
  - configured daily subscription budget;
  - remaining theoretical headroom.

No scheduled collection activation is permitted while worst-case attempts/day exceed the configured daily budget.

## Planned implementation

- migration for explicit canary/activation audit evidence;
- execution mode distinction for collection cycles;
- bounded canary runner;
- shared total request cap;
- performance + CLV diagnostic projections;
- activation-gate evaluator and reason codes;
- PostgreSQL integration tests;
- CI coverage;
- production deployment verification.

## Current decision

**BLOCKED for canary execution until shared request-cap logic is implemented and tested.**

No production variable has been changed.
