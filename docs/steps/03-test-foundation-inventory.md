# Step 03 — Test Foundation Inventory and Implementation Gates

**Status:** inventory completed; implementation gates defined
**Scope:** `Filip1994/quantbet-baseball` only

## Existing test coverage

The repository currently contains:

- `tests/test_training_dataset.py`
  - home-side target and raw implied probability;
  - post-kickoff observation exclusion;
  - non-moneyline and unknown-selection exclusion;
  - tied-result exclusion.
- `tests/test_baseball_collector.py`
  - bookmaker and market compaction behavior.

The project uses `unittest` in the training-dataset tests and plain assertion-style tests in the collector tests. `pytest` is configured as the test runner through `pyproject.toml` and `requirements-dev.txt`.

## Required next test layers

### 1. Time and leakage contracts

Add deterministic fixtures proving that:

- timezone-aware timestamps are required;
- observations at or after kickoff are excluded;
- provider publication/effective timestamps cannot be replaced silently by collection time;
- post-kickoff lineup, injury, score, and closing-market records never enter a pre-game snapshot;
- final scores are used only as labels, never as prediction-time features;
- duplicate observations do not silently overwrite one another.

### 2. Market and selection contracts

Add tests for:

- accepted two-way moneyline market names;
- rejection of run line, spread, total, inning, player, and strikeout markets;
- home/away selection mapping;
- unknown team aliases and draw selections;
- invalid, non-finite, and out-of-range odds;
- explicit handling of postponed, suspended, cancelled, aborted, and resumed games;
- extra-inning completion semantics.

### 3. Probability and baseline contracts

Add tests for:

- implied probability conversion;
- two-way de-vig normalization;
- probability bounds and normalization;
- game-level rather than row-level aggregation;
- separation of descriptive market baselines from model performance and profitability metrics.

### 4. Operational contracts

Add tests for:

- deterministic cache keys;
- raw-evidence checksum and schema metadata;
- idempotent ingestion;
- malformed provider payload quarantine;
- safe behavior when API budget is exhausted;
- paper-mode safety gates and explicit abstention decisions.

## CI acceptance gates

The test workflow is not considered complete until it runs, at minimum:

1. dependency installation;
2. formatting/lint checks;
3. Python compilation/import checks;
4. all unit and integration tests;
5. leakage and contract tests;
6. documentation/configuration validation;
7. checks preventing secrets and large raw data artifacts from entering source control.

## Implementation rule

Tests that expose a defect must be committed before the corresponding production fix. No Railway migration, live betting capability, or model-promotion work is authorized until the leakage, market-contract, and paper-safety gates are green.
