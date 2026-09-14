# Step 02 — Detailed Repository Audit

**Date:** 2026-09-14  
**Status:** Preliminary findings recorded; execution verification still required.

## Scope

This audit covers the standalone `Filip1994/quantbet-baseball` repository only. The football project and its Railway resources are explicitly out of scope and must remain isolated.

## Confirmed components reviewed

- `src/quantbot/baseball/api.py`
- `src/quantbot/baseball/config.py`
- `src/quantbot/baseball/results.py`
- `src/quantbot/baseball/training_dataset.py`
- `src/quantbot/baseball/baseline.py`
- `src/quantbot/baseball/signals.py`
- `pyproject.toml`
- `README.md` and `BASEBALL.md`

## Findings

### 1. API client and raw evidence

The API client has useful foundations: request budgeting, persistent cache paths, retry-related settings, hashed cache naming, and raw envelope archiving. The archive is written through a temporary file before replacement, which is a good durability pattern.

**Open risks:** raw archives need explicit checksum, provider/schema version, request outcome, and immutability/retention rules. The audit must also verify that failed or malformed responses cannot be mistaken for valid evidence.

**Disposition:** retain concept; harden with tests and an evidence schema.

### 2. Configuration

Configuration is baseball-specific and uses baseball-prefixed environment variables such as `API_BASEBALL_KEY` and `BASEBALL_API_REQUEST_BUDGET`. `PAPER_MODE` defaults to enabled.

**Open risks:** numeric environment parsing can raise unclassified `ValueError`; there is no visible explicit validation that the API key exists when a live request is attempted; `PAPER_MODE` needs to become a hard safety gate rather than only a configuration value.

**Disposition:** adapt and add fail-closed validation tests.

### 3. Results collection

Results are normalized from the Baseball API and include game identifiers, dates, teams, scores, status, capture time, and source.

**Open risks:** the current result writer overwrites the target JSONL file rather than clearly implementing append-only evidence or versioned snapshots. Settlement semantics for postponed, suspended, cancelled, resumed, and extra-inning games require an explicit domain policy. Team identity is not yet demonstrated to be canonical across all feeds.

**Disposition:** redesign around immutable raw results plus idempotent normalized records.

### 4. Training dataset

The current dataset builder correctly rejects observations captured at or after kickoff and excludes unresolved/tied score rows. It filters toward two-way moneyline selections and uses final scores only as labels.

**Critical risks:**

- timestamps are parsed independently, but timezone-awareness consistency is not enforced;
- moneyline detection is token-based and may accept unintended market names containing `winner`;
- selection matching is based on team-name equality, so aliases and provider naming changes can drop valid rows;
- the result mapping can silently overwrite duplicate game IDs;
- no explicit provider publication/effective timestamp is enforced, only `captured_at`;
- bookmaker/market snapshots are not yet converted into a canonical, de-vigged game-level market state;
- the current grouping key does not deduplicate equivalent observations across sources.

**Disposition:** keep as an experimental baseline only; add strict contracts and identity resolution before model use.

### 5. Baseline evaluation

The raw implied-probability evaluator provides Brier score, log loss, and accuracy and explicitly labels itself descriptive rather than a profitability claim.

**Critical risk:** raw implied probabilities are not de-vigged and individual bookmaker selections are evaluated as independent rows. This can distort interpretation and overweight games with more observations. Evaluation must be game/snapshot aware and must distinguish calibration from betting profitability.

**Disposition:** retain as diagnostic baseline; build a proper market baseline and chronological evaluation layer.

### 6. Signal layer

The signal scanner is paper-only in intent and creates immutable-looking signal records with timestamps and entry snapshot references.

**Critical risks:** thresholds are hardcoded (`EV >= 10%` and edge `>= 5pp`); the scanner trusts prediction fields without validating model version, calibration status, odds freshness, market support, or timestamp lineage; the decision string `UPLATI SADA` is unsuitable for a system that must remain paper-only and should be replaced by an explicit paper decision enum.

**Disposition:** quarantine for redesign after prediction and governance schemas are defined.

### 7. Packaging and test configuration

`pyproject.toml` declares Python `>=3.12`, no runtime dependencies, and pytest configuration. This is lightweight, but the planned CI contract requires verification of the actual test runner, formatting/linting, compile checks, and deterministic offline execution.

**Open risks:** the declared pytest configuration does not itself prove that tests exist or that CI executes all required safety suites. Dependency-free packaging may be intentional, but any statistical/modeling dependencies must be introduced deliberately and pinned.

## Priority remediation list

1. Add deterministic domain fixtures and execute the full test suite.
2. Define canonical identities and strict market/selection contracts.
3. Enforce timezone-aware, point-in-time timestamps, including provider publication/effective time.
4. Replace overwrite-style result handling with immutable evidence plus idempotent normalization.
5. Implement game-level de-vigged market baselines.
6. Redesign signal eligibility and paper decision semantics.
7. Add model/data lineage and explicit model-promotion gates.
8. Verify CI with compile, tests, leakage checks, and secret/raw-data protections.

## Audit conclusion

The repository has a useful collection and paper-trading foundation, but it is **not production-ready**. The highest-risk areas are timestamp lineage, canonical identity resolution, result immutability, market normalization, and the current signal layer's reliance on unvalidated prediction fields. No live betting or Railway migration should proceed until these controls are implemented and tested.
