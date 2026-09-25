# QuantBet Baseball — Completion Audit and QuantBet-Parity Plan

**Repository:** `Filip1994/quantbet-baseball`  
**Audited branch baseline:** `main@412e73703bc4366047ba02b64dbb3bd30c48b7a2`  
**Audit date:** 2026-09-25 Europe/Belgrade  
**Revision:** 1.0  
**Status:** CANONICAL COMPLETION AUDIT — execution baseline

## 1. Executive conclusion

QuantBet Baseball has a credible infrastructure and evidence foundation, but it is **not yet a closed betting engine**.

The current system has:

- a real Railway service;
- Railway PostgreSQL;
- Railway object storage for raw provider payloads;
- a 15-minute Railway cron;
- migration execution;
- durable append-only moneyline evidence ingestion code;
- deterministic/idempotent canonical odds identities;
- database constraints for immutable odds observations and pick events;
- unit/integration-test coverage for important evidence primitives;
- primitive market math, Poisson moneyline math, value math, decisions, and signals.

The current system does **not** yet have a production path that closes this lifecycle:

```text
fixture discovery
→ canonical market evidence
→ point-in-time model probability
→ value evaluation
→ preliminary candidate
→ mandatory final quote verification
→ immutable registered pick
→ post-pick monitoring
→ closing quote finalization
→ authoritative result
→ settlement
→ realized CLV
→ performance evaluation
```

This lifecycle is the architectural standard already established in QuantBet football. Baseball should reuse that **operating logic**, but not football-specific probability mathematics.

### Current go/no-go decision

**GO:** complete the Moneyline Closed Loop v1 using QuantBet lifecycle discipline.

**NO-GO:** turning on full production collection, expanding the model, adding more markets, or claiming edge/profitability before the closed loop and validation gates are complete.

---

## 2. What was verified on 2026-09-25

### 2.1 GitHub

Verified repository head:

`412e73703bc4366047ba02b64dbb3bd30c48b7a2` — **Make global Baseball CI green**

Important later milestones that were missing from the old progress document:

- `c1da18f14` — Railway PostgreSQL runtime foundation;
- `968b1b191` — durable canonical Baseball ingestion;
- `412e73703` — global Baseball CI cleanup/green baseline.

The repository therefore progressed materially beyond the 2026-09-15 documentation state.

### 2.2 Railway

Verified production project:

- project: `believable-contentment`;
- environment: `production`;
- service: `quantbet-baseball`;
- PostgreSQL service: `Postgres`;
- raw object bucket: `quantbet-baseball-raw-payloads`.

Verified Baseball service configuration:

- source: `Filip1994/quantbet-baseball`, branch `main`;
- start command: `PYTHONPATH=src python -m quantbot.baseball.worker`;
- pre-deploy migration command is configured;
- cron: `*/15 * * * *`;
- latest inspected deployment is `SUCCESS`.

### 2.3 Critical runtime fact

Railway runtime logs on 2026-09-25 repeatedly report:

- `collection_enabled=false`;
- `mode="storage-ready"`;
- `status="ready"`.

Therefore the cron is alive but the production collector is intentionally **disabled**.

This is not a scheduler failure. It is a feature/configuration gate.

### 2.4 Database state that was directly observable

The production database exposes:

- `schema_migrations`;
- `odds_observations`;
- `pick_events`.

A read-only inspection utility showed:

- `pick_events` total = **0**;
- no earliest pick event exists.

Exact `odds_observations` row count and freshness were not established by the available read-only connector path during this audit, so no unsupported row-count claim is made.

---

## 3. Current component audit

| Component | Status | Evidence / consequence |
|---|---|---|
| Railway runtime | IMPLEMENTED | Real service, cron, start command, migration step |
| PostgreSQL | IMPLEMENTED | Production DB exists and migrations are applied |
| Raw object archive | IMPLEMENTED | Railway bucket exists; durable collector requires remote archive |
| API budget control | IMPLEMENTED | Bounded per-run client/collector behavior |
| Canonical moneyline ingestion | IMPLEMENTED | Strict pregame mapping into `OddsObservation` |
| Canonical totals ingestion | MISSING | Schema allows `total`, production mapper is moneyline-only |
| Fixture registry/history | MISSING | No canonical persisted fixture/status history in current DB schema |
| Market timeline primitives | PARTIAL | Python timeline helpers exist; no full durable pick-linked lifecycle |
| Model math primitives | PARTIAL | Poisson/value/de-vig helpers exist |
| Point-in-time feature snapshots | MISSING | No durable production feature snapshot contract/path |
| Versioned prediction events | MISSING | No durable production prediction lifecycle |
| Value evaluation pipeline | MISSING | Helpers exist, not wired from Postgres evidence to durable evaluation |
| Final quote verification | MISSING | No mandatory re-pull/reprice boundary before registration |
| Immutable registered picks | PARTIAL | `pick_events` schema exists; no production registration path; DB has 0 picks |
| Post-pick monitoring | MISSING | No durable registered-pick monitoring state/worker |
| Opening/current/closing checkpoints | MISSING AS CLOSED LOOP | Timeline helpers do not provide production finalization |
| Results ingestion | MISSING | No canonical production result observation/state tables |
| Settlement | MISSING | No moneyline/totals settlement event lifecycle |
| Realized CLV | MISSING | No durable CLV fact/finalization path |
| Performance ledger | MISSING | No production ROI/yield/P&L evaluation lifecycle |
| Daily actionable bulletin | MISSING AS DB-BACKED PRODUCT | Legacy file/dashboard artifacts are not canonical production truth |
| Dashboard/API | LEGACY/PARTIAL | Existing static JSON/dashboard is not backed by the new DB lifecycle |
| Research separation | CONCEPTUALLY DEFINED | Needs durable datasets/versioned experiments |
| Walk-forward validation | NOT COMPLETE | No launch-grade chronological holdout report |
| Production betting readiness | NO | Paper/research only |

---

## 4. Architectural drift and documentation debt

Several active documents describe a state that is no longer true.

### `BASEBALL_PROGRESS.md`

It ends at the 2026-09-15 Railway decision and omits:

- real Railway runtime creation;
- PostgreSQL provisioning;
- object storage;
- durable ingestion;
- production migration execution;
- successful Railway deployment;
- current disabled-collection gate.

### `docs/BASEBALL_MASTER_PLAN.md`

Revision 3.1 still says durable PostgreSQL persistence is pending and says not to build Railway yet. Both statements are obsolete.

### `BASEBALL.md`

It still describes:

- 30-minute ingestion;
- up to 199 odds calls per run;
- old Git-oriented data path;
- run line as initial scope;
- player props as a later possibility.

Those statements conflict with the current 15-minute Railway design and the permanent project exclusion of player props.

Documentation must be corrected before further development so Codex/agents do not execute against obsolete architecture.

---

## 5. QuantBet logic that Baseball should inherit

Baseball should inherit **lifecycle and production engineering patterns** from `Filip1994/v2quantbet`.

### 5.1 Inherit

1. **Fixture discovery independent of betting qualification.**
2. **Append-only quote history.**
3. **Exact market/selection/bookmaker identity.**
4. **Point-in-time model inputs and versioned outputs.**
5. **Preliminary opportunity evaluation.**
6. **Mandatory final quote pull and repricing before registration.**
7. **Immutable pick registration with complete provenance.**
8. **Bounded workers with explicit cursors, retries, freshness and API budget accounting.**
9. **Post-pick monitoring until first pitch.**
10. **First / pick / current / closing quote checkpoints.**
11. **Authoritative result acquisition with stability/finality rules.**
12. **Append-only settlement events.**
13. **Realized CLV only after valid closing provenance exists.**
14. **Operational dashboard as a projection of canonical DB facts.**
15. **Strict production/research boundary.**
16. **Chronological out-of-sample / walk-forward promotion gate.**

### 5.2 Do not inherit blindly

Do not copy:

- football market definitions;
- football settlement rules;
- football feature/model mathematics;
- football league filters;
- football goal-model assumptions;
- football-specific closing proxies.

The Baseball model remains Baseball-specific.

---

## 6. Target Baseball production lifecycle

### 6.1 Canonical lifecycle

```text
DISCOVERED
  ↓
OBSERVING
  ↓
MODEL_READY
  ↓
EVALUATED
  ↓
PRELIMINARY_CANDIDATE
  ↓
FINAL_QUOTE_VERIFIED
  ↓
REGISTERED_PICK
  ↓
MONITORING
  ↓
CLOSED_FOR_ODDS
  ↓
RESULT_STABLE
  ↓
SETTLED
  ↓
CLV_FINALIZED
  ↓
EVALUATED
```

Every transition must be reconstructable from stored evidence.

### 6.2 Fail-closed states

At minimum:

- NO_ODDS;
- STALE_ODDS;
- INCOMPLETE_MARKET;
- MODEL_UNAVAILABLE;
- INSUFFICIENT_FEATURES;
- FINAL_QUOTE_REJECTED;
- API_BUDGET_EXHAUSTED;
- PROVIDER_ERROR;
- POSTPONED;
- CANCELLED;
- RESULT_UNSTABLE;
- SETTLEMENT_BLOCKED;
- PROVENANCE_CONFLICT.

A missing input is never silently imputed into a production pick unless the exact imputation method is a versioned, validated model feature.

---

## 7. Moneyline Closed Loop v1 — mandatory first completion target

The first finished product slice is **full-game moneyline only**.

It is complete only when one synthetic/test fixture and then one real paper fixture can pass the entire lifecycle without manual database edits.

### Gate ML-1 — Fixture evidence

Persist:

- provider game ID;
- league;
- home/away teams;
- scheduled first pitch;
- game status;
- observation time;
- raw payload reference/checksum.

Kickoff/status changes must be observations, not destructive overwrites.

### Gate ML-2 — Market evidence

Persist exact pregame moneyline quotes by:

- game;
- bookmaker;
- side;
- price;
- observed time;
- retrieved time;
- source payload.

Reject post-first-pitch evidence from decision/closing use.

### Gate ML-3 — Model evidence

Persist:

- feature snapshot ID;
- feature cutoff;
- model version;
- model probability;
- uncertainty/calibration metadata;
- prediction time.

Production prediction code may initially use a simple validated baseline. The lifecycle must not depend on a complex model being finished.

### Gate ML-4 — Value evaluation

Persist the exact:

- model probability;
- de-vigged market probability;
- fair odds;
- offered odds;
- edge;
- EV;
- uncertainty gate;
- rejection/approval reasons.

### Gate ML-5 — Final quote verification

Before any pick is registered:

1. re-fetch the exact market;
2. verify game has not started;
3. verify quote freshness;
4. verify exact bookmaker/selection identity;
5. reprice EV using the returned quote;
6. register only if thresholds still pass.

No candidate becomes a pick from a stale preliminary quote.

### Gate ML-6 — Immutable pick

A registered pick must preserve:

- game/market/selection;
- bookmaker/source;
- exact entry odds;
- entry snapshot ID;
- model/evaluation IDs;
- registration timestamp;
- decision policy version;
- paper stake/bankroll metadata where enabled.

### Gate ML-7 — Monitoring and closing

After registration:

- prioritize pick quotes in API budget;
- keep monitoring until first pitch;
- finalize one closing fact;
- explicitly record CAPTURED / STALE / NO_VALID_QUOTE.

Closing must never be reconstructed after the fact from unknown data.

### Gate ML-8 — Result and settlement

Acquire authoritative final game result and stabilize it before settlement.

Moneyline settlement must explicitly define:

- completed game;
- cancellation/postponement;
- suspended/abandoned cases;
- provider correction handling;
- bookmaker-rule assumptions.

### Gate ML-9 — CLV and evaluation

After settlement and closing finalization:

- calculate realized CLV from exact entry/closing prices;
- preserve method version;
- record outcome, P&L, ROI/yield inputs, and evaluation metadata.

---

## 8. Totals Closed Loop v1

Totals are implemented only after Moneyline Closed Loop v1 is green.

Totals require additional explicit contracts:

- canonical numeric line identity;
- over/under selection identity;
- exact line matching during quote monitoring;
- push semantics for integer lines if ever admitted;
- game-total settlement rules;
- model distribution of total runs;
- line-specific calibration/validation.

Initial totals should remain limited to lines with enough real historical coverage. The old examples 8.5/9.5 are hypotheses, not guaranteed production lines.

---

## 9. Data/model research gates

The lifecycle can be built before the final model is strong. Betting qualification cannot.

### Minimum research outputs before any profitability claim

- chronological train/validation/untouched holdout split;
- calibration plot/table;
- log loss;
- Brier score;
- coverage/abstention rate;
- ROI and yield with exact historical executable prices;
- realized CLV distribution;
- max drawdown;
- performance by league/bookmaker/time-to-start;
- stale-quote sensitivity;
- model-version comparison;
- bootstrap/confidence intervals where appropriate;
- leakage audit.

### Promotion rule

```text
research hypothesis
→ versioned experiment
→ chronological evaluation
→ walk-forward / untouched holdout
→ documented acceptance
→ explicit production model version
→ regression tests
```

No research notebook or in-sample result changes production behavior automatically.

---

## 10. Production activation rule

Do **not** set `BASEBALL_ENABLE_COLLECTION=true` yet.

Current cadence and budget are designed near the 7,500 requests/day subscription ceiling. Enabling collection before the lifecycle consumes real quota while producing only moneyline observations and no closed pick/evaluation loop.

Collection activation requires:

1. canonical fixture persistence;
2. durable runtime-cycle telemetry;
3. verified moneyline quote persistence;
4. exact DB freshness/coverage dashboard query;
5. downstream paper lifecycle ready to consume observations;
6. API budget headroom calculation including retries;
7. one controlled canary collection run;
8. verified raw archive + PostgreSQL writes;
9. no duplicate/conflict anomalies.

Then enable in paper mode only.

---

## 11. Execution order from this audit

### Package A — Canonical runtime truth

- correct stale documentation;
- persist fixture observations;
- persist collection-run telemetry;
- expose DB health/freshness counts;
- add controlled collector canary command;
- leave scheduled collection disabled.

### Package B — Moneyline decision chain

- feature/prediction event contract;
- market snapshot construction from canonical DB evidence;
- value evaluation event;
- final quote verification;
- immutable pick registration;
- end-to-end tests through registration.

### Package C — Monitoring and closing

- registered-pick monitoring state;
- budget priority for active picks;
- current/opening/pick/closing projections;
- closing finalization;
- restart/idempotency tests.

### Package D — Result, settlement, CLV

- result observations and finality;
- Baseball moneyline settlement rules;
- settlement events;
- realized CLV facts;
- performance projection.

### Package E — Operational product

- DB-backed daily bulletin;
- dashboard/API;
- worker observability;
- alerts for stale/no-data/budget conditions;
- restore/replay test.

### Package F — Research/model validation

- historical canonical backfill;
- point-in-time features;
- baseline models;
- calibration;
- walk-forward;
- untouched holdout;
- promotion decision.

### Package G — Totals

Repeat Packages B–F for full-game totals with exact line identity.

---

## 12. Definition of done

QuantBet Baseball is **finished as a paper betting engine** only when all of the following are true:

- Railway is the sole production runtime/control plane;
- PostgreSQL/object storage are the canonical operational evidence stores;
- collection is active, budget-safe and observable;
- moneyline and approved totals can traverse the complete lifecycle;
- every pick is reproducible from immutable inputs;
- final quote verification is mandatory;
- monitoring and closing are deterministic and restart-safe;
- results are stabilized before settlement;
- realized CLV has exact quote provenance;
- dashboard/bulletin read from canonical DB facts;
- full CI covers the closed lifecycle;
- restore/replay has been tested;
- chronological validation and untouched holdout are documented;
- the system remains `PAPER_MODE=true` until a separate explicit launch decision.

A successful deployment, a working collector, or a profitable short sample is not sufficient.

---

## 13. Immediate engineering decision

The project should now be run as a sequence of **closed vertical slices**, not more exploratory feature additions.

The next implementation target is:

> **Package A → Package B, Moneyline only, with production collection still disabled.**

That is the shortest path from the current repository to the QuantBet architecture without wasting API quota or creating a second partial system.
