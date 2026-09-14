# Step 01 — Test and CI Gates

**Status:** Planned  
**Owner:** Project implementation  
**Dependency:** Step 00 audit

## Goal

Make correctness and safety executable. Tests must fail before unsafe behavior can reach the default branch or Railway.

## Test layers

### Unit tests

- decimal odds to implied probability;
- vig removal for two-way markets;
- probability bounds and numerical stability;
- team and selection normalization;
- timestamp comparison and kickoff cutoff;
- model output schema;
- expected-run and win-probability calculations;
- unknown market/selection rejection;
- tie and postponed-game handling.

### Leakage tests

Create fixtures containing:

- pre-kickoff snapshots;
- post-kickoff snapshots;
- late lineup and injury updates;
- final scores;
- closing odds.

Assert that a prediction generated at time `T` can consume only records whose effective timestamp is `<= T` and whose publication/availability timestamp is also valid.

### Contract tests

Validate provider payloads, required identifiers, market names, odds format, timezone handling, and missing/null behavior. Unknown values must fail closed or be quarantined.

### Integration tests

Test ingestion -> normalization -> storage -> feature snapshot -> prediction -> settlement using deterministic fixtures.

### Regression tests

Pin known historical cases and expected outputs. Every bug becomes a regression fixture before it is fixed.

## CI gates

1. Install dependencies.
2. Run formatting/lint checks.
3. Run unit and integration tests.
4. Run leakage and contract suites.
5. Validate documentation links and configuration templates.
6. Fail on secret-like files or accidental raw-data additions.

## Definition of done

- Tests are deterministic and runnable without paid API access.
- Critical tests cover all supported markets.
- CI runs on pull requests and pushes to the default branch.
- A failed critical test blocks deployment.
- Test results and known limitations are recorded in `BASEBALL_PROGRESS.md`.
