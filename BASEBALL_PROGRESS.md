

## 11. Documentation and migration planning milestone — 2026-09-14

The project plan was expanded into a documented execution program from the current state through launch.

Added:

- `docs/BASEBALL_MASTER_PLAN.md` — complete plan, workstreams, target architecture, baseball mathematics scope, Railway migration sequence, and launch acceptance criteria;
- `docs/steps/00-repository-and-legacy-audit.md` — detailed audit procedure and safety rules;
- `docs/steps/01-test-and-ci-gates.md` — detailed test strategy, leakage controls, contracts, integration tests, and CI gates;
- `docs/LEGACY_PORTING_MATRIX.md` — preliminary classification of legacy `Filip1994/h2h` components.

The target repository is confirmed as `Filip1994/quantbet-baseball`. The `Filip1994/h2h` repository is treated as legacy and read-only. Its Dixon–Coles-related concepts, calibration, closing, registry, settlement, and operational patterns may be considered for adaptation only after component-level review and baseball-specific tests.

No production data was deleted, no destructive migration was executed, and no live betting capability was enabled.

## 12. Test foundation and CI hardening milestone — 2026-09-14

Added the first training-dataset contract tests in `tests/test_training_dataset_contracts.py`, covering:

- away-team winner target assignment;
- rejection of invalid/non-positive odds;
- exclusion of postponed games without a settled result;
- deduplication of identical game snapshot/side observations;
- exclusion of observations captured exactly at kickoff.

Hardened `.github/workflows/tests.yml`:

- added `python -m compileall -q src tests` as an explicit syntax/bytecode gate;
- replaced mutating `ruff format .` with non-mutating `ruff format --check .`;
- retained `ruff check .` and `pytest` as required gates.

The CI workflow now validates formatting instead of modifying the checkout during CI. Test execution has not been independently confirmed in a local runtime yet.

Commits:

- `5110c19ca9e08e1835708932a1a22dee869b93ae` — training-dataset contract tests;
- `61a597b1b00ee0bf06f69f49473de47a6a8d7ec0` — CI hardening.

## 13. Timestamp contract milestone — 2026-09-14

Added `tests/test_timestamp_contracts.py` covering:

- `Z` timestamps are parsed as UTC-aware datetimes;
- naive observation timestamps are rejected;
- malformed timestamps are rejected.

Updated `src/quantbot/baseball/training_dataset.py` so `_parse_time()` accepts only timezone-aware timestamps. This prevents silent interpretation of ambiguous local times in pre-kickoff leakage checks.

Commits:

- `b1c9d7d31fe536ce78b712a38a37cb4978d5a91e` — timestamp contract tests;
- `d65724e9c3a3e4e1a1b79a83e0bf2170e56af3dd` — reject naive training timestamps.

## 14. Market contract milestone — 2026-09-14

Tightened `_is_moneyline()` in `src/quantbot/baseball/training_dataset.py` to accept only explicit full-game winner/result market labels:

- `moneyline`;
- `match winner`;
- `game winner`;
- `match result`;
- `game result`.

Ambiguous markets such as first-five innings, player props, run line, totals, and series winner are now excluded instead of relying on broad substring matching.

Added `tests/test_market_contracts.py` covering accepted labels, rejected market types, and enforcement during row creation.

Commits:

- `80df7e88c6b7b36132e7bf2acb5d6feca4c7767b` — strict market contract;
- `56e2f7a2365f2f5b5df53755f51251b6a2311f2b` — market contract tests.

Test execution has not been independently confirmed in a local runtime.
