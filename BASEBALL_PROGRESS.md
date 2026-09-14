

## 11. Documentation and migration planning milestone — 2026-09-14

The project plan was expanded into a documented execution program from the current state through launch.

Added:

- `docs/BASEBALL_MASTER_PLAN.md` — complete plan, workstreams, target architecture, baseball mathematics scope, Railway migration sequence, and launch acceptance criteria;
- `docs/steps/00-repository-and-legacy-audit.md` — detailed audit procedure and safety rules;
- `docs/LEGACY_PORTING_MATRIX.md` — preliminary classification of legacy `Filip1994/h2h` components.

The target repository is confirmed as `Filip1994/quantbet-baseball`. The `Filip1994/h2h` repository is treated as legacy and read-only. No production data was deleted, no destructive migration was executed, and no live betting capability was enabled.

## 12. Test foundation and CI hardening milestone — 2026-09-14

Added training-dataset contract tests covering away-team labels, invalid odds, postponed games, duplicate observations, and exact-kickoff exclusion.

Hardened `.github/workflows/tests.yml` with explicit compilation, non-mutating Ruff formatting checks, linting, and pytest gates. Test execution has not been independently confirmed in a local runtime.

Commits: `5110c19`, `61a597b`.

## 13. Timestamp contract milestone — 2026-09-14

Added timestamp contract tests and restricted `_parse_time()` to timezone-aware ISO timestamps. Naive and malformed timestamps are rejected to prevent ambiguous pre-kickoff leakage checks.

Commits: `b1c9d7d`, `d65724e`.

## 14. Market contract milestone — 2026-09-14

Restricted `_is_moneyline()` to explicit full-game winner/result labels: `moneyline`, `match winner`, `game winner`, `match result`, and `game result`. First-five, props, run line, totals, and series markets are excluded.

Added market contract tests.

Commits: `80df7e8`, `56e2f7a`.

## 15. Team identity and result integrity milestone — 2026-09-14

Implemented conservative team-name normalization for case, whitespace, punctuation, hyphen, and underscore differences without inventing provider aliases.

Hardened `_result_map()` to fail closed when the same game ID has conflicting settled result records. Identical duplicates remain idempotent; conflicting records are removed instead of allowing last-write-wins behavior.

Added identity/result contract tests.

Commits:

- `cf343776` — identity normalization and conflict-safe result mapping;
- `511c9177` — identity/result contract tests.

## 16. Two-way market math foundation milestone — 2026-09-14

Added `src/quantbot/baseball/market.py` with conservative market primitives:

- `devig_two_way()` proportionally removes the overround from a valid two-way probability pair;
- `aggregate_bookmaker_probabilities()` computes a bookmaker-neutral mean of valid home/away probabilities and normalizes the pair;
- invalid, missing, non-finite, or incomplete markets fail closed;
- the implementation is restricted to two mutually exclusive outcomes and does not infer missing sides.

Added `tests/test_market_math.py` covering proportional de-vig normalization, invalid inputs, duplicate-row neutrality, and incomplete-market rejection.

Important limitation: these primitives are not yet wired into the training dataset or production signal path. They establish a tested mathematical contract before integration, weighting policy, and snapshot identity are implemented.

Commits:

- `4f062c6` — two-way market math primitives;
- `f3b8ab1` — market math contract tests.

Test execution has not been independently confirmed in a local runtime.
