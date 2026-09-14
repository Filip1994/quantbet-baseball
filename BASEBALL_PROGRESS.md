

## 11. Documentation and migration planning milestone — 2026-09-14

The project plan was expanded into a documented execution program from the current state through launch.

Added:

- `docs/BASEBALL_MASTER_PLAN.md` — complete plan, workstreams, target architecture, baseball mathematics scope, Railway migration sequence, and launch acceptance criteria;
- `docs/steps/00-repository-and-legacy-audit.md` — detailed audit procedure and safety rules;
- `docs/steps/01-test-and-ci-gates.md` — detailed test strategy, leakage controls, contracts, integration tests, and CI gates;
- `docs/LEGACY_PORTING_MATRIX.md` — preliminary classification of legacy `Filip1994/h2h` components.

The target repository is confirmed as `Filip1994/quantbet-baseball`. The `Filip1994/h2h` repository is treated as legacy and read-only. Its Dixon–Coles-related concepts, calibration, closing, registry, settlement, and operational patterns may be considered for adaptation only after component-level review and baseball-specific tests.

No production data was deleted, no destructive migration was executed, and no live betting capability was enabled.
