# QuantBet Baseball — Repository Audit and Execution Layout

**Repository:** `Filip1994/quantbet-baseball`  
**Legacy reference:** `Filip1994/h2h` — read-only; not audited as an implementation target  
**Created at:** 2026-09-15 01:00 Europe/Belgrade (UTC+02:00)  
**Last updated:** 2026-09-15 01:00 Europe/Belgrade (UTC+02:00)  
**Revision:** 1.0  
**Status:** AUDIT BASELINE — implementation and runtime verification incomplete

## 1. Audit purpose

This audit establishes the current repository state before further model expansion. It distinguishes documented intent from code that exists, and code that exists from code whose tests or runtime behavior have been independently verified.

The audit was performed against the repository tree and the current master plan/progress documentation available on the default branch. No claim of local test execution is made.

## 2. Executive result

The repository contains meaningful baseball-specific foundations, but it is **not yet a closed betting system**. The current implementation is best classified as a collection of validated-in-design primitives plus data-collection artifacts and workflow scaffolding.

The largest architectural gap is the absence of a complete, immutable, replayable market timeline and pick-event lifecycle connecting:

`raw odds evidence → normalized observations → market snapshot → model decision → immutable pick event → subsequent price observations → closing price → settlement → evaluation`.

Further model complexity should not be added until this lifecycle and its evidence contracts are implemented and tested.

## 3. Verified repository observations

The repository tree contains:

- baseball documentation and progress tracking;
- GitHub Actions workflows for collection, training, and tests;
- raw API evidence under `data/baseball/raw_api/`;
- a large JSONL market-observation artifact;
- market coverage/intelligence/dashboard artifacts;
- baseball source modules for identities, training data, market math, snapshots, run modeling, value, decisions, signals, and signal records;
- environment configuration examples.

The repository head observed during this audit was associated with tree/commit:

`4159f6a6329d4007773a2cebe332e5a96027ebe5`

This identifier is recorded as the audit snapshot, not as proof that every workflow or test succeeds.

## 4. Component status

| Area | Status | Finding | Required action |
|---|---|---|---|
| Repository separation | VERIFIED | Baseball work is in `quantbet-baseball`; legacy football repo is separate | Preserve boundary |
| Documentation/progress | PARTIALLY VERIFIED | Plan and milestone log exist, but previous learning is not represented as a complete evidence ledger | Add knowledge ledger and decision records |
| Team identity normalization | IMPLEMENTED BUT UNTESTED | Conservative identity handling exists | Run and expand fixtures |
| Training dataset loader | IMPLEMENTED BUT UNTESTED | Timestamp and result guards are documented in code history | Execute tests; add leakage fixtures |
| Two-way market math | IMPLEMENTED BUT UNTESTED | De-vig and bookmaker aggregation primitives exist | Verify against hand-calculated fixtures |
| Market snapshot integrity | IMPLEMENTED BUT UNTESTED | Identity, timestamp, duplicate, and post-kickoff guards are documented | Runtime-test and persist snapshot IDs |
| Run-to-moneyline baseline | IMPLEMENTED BUT UNTESTED | Independent-Poisson baseline exists; not connected to pipeline | Test numerical behavior and limitations |
| Value/pricing primitives | IMPLEMENTED BUT UNTESTED | Fair odds, edge, and EV primitives exist | Test rounding, invalid inputs, and sign conventions |
| Decision policy | IMPLEMENTED BUT UNTESTED | Fail-closed BET/PASS gates exist | Test threshold boundaries and uncertainty gates |
| Signal builder | IMPLEMENTED BUT UNTESTED | Evaluates both sides and selects at most one | Test tie-breaking and abstention |
| Signal record envelope | IMPLEMENTED BUT UNTESTED | Minimal validated JSONL envelope exists | Extend to immutable pick-event contract |
| Odds timeline | MISSING AS COMPLETE LIFECYCLE | Raw observations exist, but no verified end-to-end opening/decision/closing timeline contract is established | Build canonical observation and timeline schema |
| Immutable pick events | MISSING AS COMPLETE LIFECYCLE | Current signal record is not sufficient for replay, execution-price audit, or later CLV | Implement pick-event schema and persistence |
| Closing-line/CLV evaluation | MISSING | No verified complete linkage from decision price to closing price | Implement timeline joins and metrics |
| Settlement | MISSING AS COMPLETE PIPELINE | Raw results/data may exist, but no verified canonical settlement lifecycle | Define market-specific settlement contracts |
| Chronological backtesting | MISSING AS VERIFIED SYSTEM | Plan exists; no independently verified holdout report is present | Build leakage-safe evaluation harness |
| Production readiness | NOT READY | No verified end-to-end evidence, restore/replay proof, or holdout gate | Remain in research/paper mode |

## 5. Data and evidence findings

1. Raw API responses are present and should remain immutable evidence.
2. The existence of raw files does not prove that their schema, completeness, provider semantics, or timestamps have been validated.
3. A large market-observation JSONL artifact exists, but its presence alone does not prove that every row has canonical market identity, reliable source lineage, bookmaker identity, line semantics, or complete timestamp semantics.
4. The system must distinguish at least:
   - provider event time, if supplied;
   - quoted/observed market time, if supplied;
   - retrieval time;
   - local ingestion time;
   - kickoff time;
   - decision time;
   - closing observation time.
5. Missing or contradictory timestamps must never be silently repaired.

## 6. Scope decision

### V1 in scope

- full-game moneyline;
- full-game totals with an explicit line, initially only lines actually present and sufficiently covered in the data, such as 8.5 and 9.5;
- timestamped odds observations;
- immutable pick events;
- settlement and post-game evaluation;
- chronological backtesting and timing/CLV research.

### Postponed

- run line;
- F5 markets;
- team totals;
- NRFI/YRFI;
- inning markets;
- alternate lines;
- futures;
- parlays and same-game parlays;
- live betting;
- automated staking.

### Explicitly excluded

- **Player props — OUT OF SCOPE.** They are not part of V1, later phases, the research curriculum, or the future roadmap for this project.

## 7. Required execution order from this audit

### Work package A — Documentation control

- maintain this audit with revision and timestamp;
- maintain `BASEBALL_PROGRESS.md` as a chronological record of material changes;
- create a knowledge ledger with source, retrieval time, fact/assumption classification, limitation, and implementation consequence;
- record decisions and rejected ideas explicitly.

### Work package B — Canonical market evidence contract

- define canonical IDs for game, market, selection, line, bookmaker, and observation;
- define timestamp semantics and timezone requirements;
- preserve raw payload checksum and source reference;
- define deduplication and conflict behavior;
- define market status/suspension behavior;
- add fixtures for stale, duplicated, conflicting, post-kickoff, and incomplete observations.

### Work package C — Immutable pick-event contract

- persist the exact market/line/selection;
- persist the exact decision-time price and market snapshot ID;
- persist model version and feature snapshot ID;
- persist fair probability, fair price, edge, EV, uncertainty, and decision reason;
- prohibit mutation after creation; corrections must be append-only events.

### Work package D — Timeline and evaluation

- link observations before and after the pick;
- identify opening, decision-time, and closing observations using explicit rules;
- calculate CLV with documented price conventions;
- support replay from raw evidence;
- add settlement contracts for each V1 market.

### Work package E — Verification gate

- run the full test suite in a real runtime;
- report exact command, environment, result, and timestamp;
- add chronological leakage tests;
- produce a first reproducible audit report before expanding the model.

## 8. Current stop/go decision

**STOP model expansion. GO on evidence architecture.**

The next major implementation package is the canonical odds-observation schema plus immutable pick-event/timeline design. Railway deployment is not the next step; it follows after the data contracts and local verification are credible.

## 9. Audit limitations

- This document records repository-level inspection, not a successful local execution.
- GitHub-visible source and workflow files do not establish that external providers are currently reachable or that scheduled workflows succeed.
- No profitability claim is made.
- No production readiness claim is made.

## 10. Completion criterion for this audit package

This audit package is complete only when:

- the scope is reflected consistently across all project documents;
- player props are removed from every active plan/roadmap section;
- the next implementation package is explicit;
- progress contains a timestamped entry referencing this audit;
- the repository commit containing these changes is recorded.
