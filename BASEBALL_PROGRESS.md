

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
