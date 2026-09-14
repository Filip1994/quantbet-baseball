

## 18. Strict market snapshot integrity milestone — 2026-09-14

Hardened `build_two_way_market_snapshot()` to prevent silent market mixing and duplicate overwrite behavior.

Added:

- required shared `game_id`, `market`, `captured_at`, and `kickoff` identity across all usable observations;
- rejection of missing, malformed, or timezone-naive timestamps;
- rejection of snapshots captured at or after kickoff;
- rejection of mixed game IDs, markets, capture timestamps, or kickoff timestamps;
- idempotent handling of exact duplicate bookmaker/side observations;
- fail-closed handling of conflicting duplicate bookmaker/side observations;
- preservation of snapshot identity in the returned result.

Updated tests cover mixed identities, post-kickoff observations, naive timestamps, exact duplicates, and conflicting duplicates.

Commits:

- `d3b40cf` — strict snapshot identity and duplicate handling;
- `7bc82c6` — expanded snapshot contract tests.

Test execution has not been independently confirmed in a local runtime.

## 19. Poisson run-to-moneyline baseline milestone — 2026-09-14

Added `src/quantbot/baseball/run_model.py` with a first mathematical baseline for converting expected home and away runs into two-way moneyline probabilities.

The baseline assumes independent Poisson scoring, excludes equal-score mass, renormalizes the remaining two-way mass, and fails closed for invalid numerical inputs or unsafe run bounds.

It is not connected to training, market snapshots, betting signals, or production services.

Commits: `538fcc3`, `a331eb2`.

Test execution has not been independently confirmed in a local runtime.

## 20. Value and pricing primitives milestone — 2026-09-15

Added `value.py` with fair decimal odds, model-minus-market edge, and expected net value per unit. Invalid and non-finite inputs fail closed.

These are mathematical building blocks only; they are not connected to decision policy, bankroll rules, calibration, or live execution.

Commits: `b6d81f6`, `dd4ba43`.

Test execution has not been independently confirmed in a local runtime.

## 21. Fail-closed moneyline decision policy milestone — 2026-09-15

Added `decision.py` with an auditable pre-game moneyline evaluator. It computes fair odds, edge, and EV; applies configurable thresholds; requires explicit uncertainty approval; and returns `PASS` with a machine-readable reason whenever a gate fails.

This does not place bets, size stakes, manage bankroll, calibrate models, or establish production readiness.

Commits: `3b412bf`, `ba587e4`.

Test execution has not been independently confirmed in a local runtime.

## 22. Two-way moneyline signal builder milestone — 2026-09-15

Added `signal.py` to evaluate both sides of one pre-game moneyline and select at most one eligible side.

The builder validates game identity and normalized two-way model probabilities, evaluates both sides through the fail-closed policy, abstains when neither side qualifies, and selects the highest-EV eligible side with edge as deterministic tie-breaker.

It does not place bets or calculate stake sizes.

Test execution has not been independently confirmed in a local runtime.

## 23. Auditable signal record envelope milestone — 2026-09-15

Added `signal_record.py` with a minimal validation and serialization boundary for signal outputs.

The envelope requires a non-empty `game_id`, a timezone-aware `generated_at`, a valid `decision` (`BET` or `PASS`), and a non-empty `reason`. It rejects malformed timestamps and non-finite numeric audit metrics, and serializes validated records deterministically as compact JSON suitable for JSON Lines storage.

This boundary does not persist records, execute bets, or imply model validity.

Test execution has not been independently confirmed in a local runtime.

## 24. Repository audit and master-plan reset — 2026-09-15 01:00 Europe/Belgrade (UTC+02:00)

Created `docs/BASEBALL_REPOSITORY_AUDIT.md` as the formal repository audit baseline. The audit separates documented intent from implemented code and from independently verified runtime behavior.

Key findings:

- baseball-specific primitives exist for identities, training data, market math, snapshots, run modeling, value, decisions, signals, and signal records;
- runtime execution and test success have not been independently confirmed;
- the project is not yet a closed replayable betting system;
- the largest gap is the complete evidence-to-pick-to-closing-line-to-settlement lifecycle;
- model expansion is paused until evidence architecture is implemented.

Revised `docs/BASEBALL_MASTER_PLAN.md` to revision 3.0 and permanently removed player props from all active scope and roadmap sections. Player props are now explicitly `OUT OF SCOPE`, not postponed.

New execution order:

1. canonical odds-observation/evidence contract;
2. immutable pick-event contract;
3. opening/decision/closing timeline and CLV linkage;
4. settlement and replayable evaluation;
5. runtime test verification;
6. only then further model expansion and Railway operations.

Artifacts:

- `docs/BASEBALL_REPOSITORY_AUDIT.md` — revision 1.0;
- `docs/BASEBALL_MASTER_PLAN.md` — revision 3.0.

Commits:

- `a1449c0` — repository audit and execution layout;
- `d5da992` — master-plan revision and permanent player-props exclusion.

Runtime tests were not executed by this audit package.

## 25. Odds timeline and pick-event specification — 2026-09-15 01:00 Europe/Belgrade (UTC+02:00)

Created `docs/ODDS_TIMELINE_AND_PICK_EVENT_SPEC.md`, revision 1.0.

This is the design baseline for the next implementation package. It defines:

- immutable market observations;
- exact market identity and line handling;
- provider versus retrieval timestamps;
- source payload references and checksums;
- immutable `BET` and `PASS` pick events;
- opening, decision, and observed closing semantics;
- stale-price and line-change handling;
- CLV requirements;
- separate settlement records;
- replay and leakage rejection rules;
- implementation order and acceptance criteria.

Player props are explicitly marked `OUT OF SCOPE` in this specification.

Commit:

- `accf02b` — define odds timeline and immutable pick event contract.

No production code was added in this milestone. Runtime tests were not executed.

## 26. Canonical evidence contracts — 2026-09-15

Added `src/quantbot/baseball/evidence.py` as the first implementation boundary for the evidence lifecycle.

Implemented:

- immutable `OddsObservation` contract for moneyline and full-game total observations;
- immutable `PickEvent` contract for both `BET` and retained `PASS` decisions;
- strict timezone-aware timestamp validation;
- rejection of post-kickoff pre-game observations;
- decimal-odds, probability, finite-number, market-family, line, and status validation;
- explicit null metrics for `PASS` events rather than fabricated values;
- deterministic compact JSON serialization;
- deterministic SHA-256 hashing helper for source payloads.

The module is storage-agnostic and is not yet connected to persistence, timeline reconstruction, settlement, or Railway.

Commit:

- `ccbe8d4` — add canonical odds and pick evidence contracts.

Runtime tests were not independently executed in this environment.
