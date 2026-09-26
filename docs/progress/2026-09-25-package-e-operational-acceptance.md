# QuantBet Baseball — Package E Operational Acceptance Worklog

**Date:** 2026-09-25  
**Branch:** `finish/package-e-canary-acceptance-20260925`  
**Repository:** `Filip1994/quantbet-baseball`  
**Railway project:** `believable-contentment`

## Non-negotiable guardrails

- Baseball only.
- Football Railway project is untouched.
- Football repository is untouched.
- Scheduled collection remains disabled.
- Paper mode remains mandatory.
- Canary execution must be bounded and separately identifiable.
- Every activation decision must be reconstructable from durable evidence.

## Package D production closure

Package D was verified before starting this package.

GitHub:

- PR #8 is merged.
- Merge commit: `0f1126fec305de58562c5551b0d81f36df7a2b9a`.
- PR head workflows:
  - Baseball tests: SUCCESS;
  - Railway runtime smoke: SUCCESS.

Railway:

- deployment: `1fc35c1d-9c1c-4843-b52e-154cb60411f9`;
- status: SUCCESS;
- migration log:
  - `006_moneyline_settlement_clv.sql` applied;
- storage-ready cron continues successfully;
- `BASEBALL_ENABLE_COLLECTION` remains effectively false.

## Package E target

Build the explicit boundary between “code is green” and “production collection may be activated”.

Target states:

```text
BLOCKED
→ READY_FOR_CANARY
→ CANARY_PASSED
→ READY_FOR_SCHEDULED_COLLECTION
```

The system must explain every blocked gate with concrete reason codes.

## Existing activation criteria recovered from project docs

Before scheduled collection activation:

1. lifecycle slices are green;
2. exact API budget math including retries is verified;
3. one bounded canary succeeds;
4. DB freshness/coverage is visible;
5. raw archive writes are verified;
6. no identity conflicts occur;
7. downstream paper lifecycle is ready to consume evidence;
8. production remains PAPER_MODE=true.

## Critical budget defect found

The pre-monitoring collector used:

- 2 schedule requests per cron cycle;
- up to 76 odds requests;
- 78 maximum provider attempts per 15-minute cycle;
- 96 cycles/day;
- 78 × 96 = 7,488 attempts/day.

This fit under a 7,500 request/day subscription ceiling with only 12 requests of theoretical headroom.

The closed lifecycle now also has higher-priority provider work:

- settlement refresh:
  - up to one game request per due closed pick;
- monitoring refresh:
  - one game request per due active pick;
  - potentially one odds request per due active pick;
- broad collector:
  - two schedule requests;
  - remaining broad odds requests.

Current code only reduces the broad odds allowance by monitoring odds calls. It does not subtract every settlement/fixture call from the old 76-odds budget.

Therefore the old cap is no longer a valid daily ceiling.

## Required budget design

Package E will replace the effective “odds-only cap” with a shared total fresh-request budget per cron cycle.

Principles:

- settlement gets first priority;
- monitoring gets second priority;
- broad schedule discovery must reserve two calls;
- broad odds collection gets only remaining capacity;
- retries count because `BaseballAPIClient.request_count` increments before every HTTP attempt;
- the acceptance report must expose:
  - cron cycles/day;
  - per-cycle request cap;
  - worst-case attempts/day;
  - configured daily subscription budget;
  - remaining theoretical headroom.

No scheduled collection activation is permitted while worst-case attempts/day exceed the configured daily budget.

## Planned implementation

- migration for explicit canary/activation audit evidence;
- execution mode distinction for collection cycles;
- bounded canary runner;
- shared total request cap;
- performance + CLV diagnostic projections;
- activation-gate evaluator and reason codes;
- PostgreSQL integration tests;
- CI coverage;
- production deployment verification.

## Current decision

**BLOCKED for canary execution until shared request-cap logic is implemented and tested.**

No production variable has been changed.


## Implementation update — shared request cap, canary evidence, gate and diagnostics

Package E implementation now contains the following.

### Shared total API request cap

Updated `src/quantbot/baseball/durable_collector.py`.

New behavior:

- `BASEBALL_MAX_API_REQUESTS_PER_CYCLE` defaults to **75**;
- the production `BaseballAPIClient` is constructed with that per-cycle cap;
- every fresh HTTP attempt increments the same `request_count`;
- retries, settlement refreshes, monitoring fixture refreshes, monitoring odds refreshes, schedule discovery and broad odds calls therefore share one hard ceiling;
- `remaining_broad_odds_capacity()` reserves two schedule calls and gives the broad odds lane only the remaining capacity;
- lifecycle work remains priority-ordered:
  1. settlement;
  2. monitoring;
  3. broad collection.

Budget math with current defaults:

- 15-minute cadence = 96 cycles/day;
- 75 attempts/cycle × 96 = **7,200 attempts/day** worst case;
- configured daily ceiling = 7,500;
- theoretical headroom = **300 attempts/day**;
- default required operational reserve = **250 attempts/day**.

The previous 78-attempt design would produce 7,488 worst-case attempts/day and only 12 requests of headroom, so the new gate deliberately rejects that configuration.

### Collection execution mode

Updated:

- `runtime_evidence.py`;
- `postgres_repository.py`;
- migration `007_operational_acceptance.sql`.

`collection_cycles` now distinguishes:

- `SCHEDULED`;
- `CANARY`.

This keeps a bounded canary auditable and prevents it from being confused with normal scheduled production collection.

### Migration 007

Added `migrations/007_operational_acceptance.sql`.

It adds:

- `collection_cycles.execution_mode`;
- immutable `operational_canary_runs`;
- immutable `activation_gate_assessments`;
- `baseball_moneyline_evaluation_rows`;
- `baseball_moneyline_performance`;
- `baseball_moneyline_performance_breakdown`.

Performance projections expose:

- settled picks;
- wins/losses/pushes;
- unit P&L;
- ROI per unit staked;
- Brier score;
- log loss;
- CLV availability/coverage;
- average probability CLV;
- average price-ratio CLV;
- positive CLV rate;
- model-version and bookmaker breakdowns.

### Canary runner

Added `src/quantbot/baseball/canary.py`.

Safety rules:

- refuses to run if `BASEBALL_ENABLE_COLLECTION=true`;
- requires explicit `BASEBALL_ENABLE_CANARY=true`;
- defaults to only 8 total fresh provider attempts;
- uses the same archive/database collector path as production;
- persists a durable canary fact.

A canary can pass only if:

- at least one provider request occurred;
- there were zero collection errors;
- both fixture and odds PostgreSQL writes are verified;
- both fixture and odds evidence point to remote `s3://` archive objects;
- the collection cycle is explicitly marked `CANARY`.

No canary has been executed in production yet.

### Activation gate

Added `src/quantbot/baseball/activation_gate.py`.

Targets:

- `CANARY`;
- `SCHEDULED_COLLECTION`.

Current checks include:

- PAPER_MODE enabled;
- scheduled collection still disabled before activation;
- API key configured;
- full raw archive configuration present;
- migrations current;
- recent Railway runtime cycle;
- safe daily request math and required reserve;
- recent successful canary for scheduled activation.

Every assessment is persisted with exact budget inputs and reason codes.

### Tests added

Added:

- `tests/test_operational_acceptance.py`;
- `tests/test_operational_postgres_integration.py`.

Extended:

- `tests/test_durable_collector.py`.

Tests explicitly prove:

- 75/cycle → 7,200/day → 300 headroom → budget-safe;
- 78/cycle → only 12 headroom → blocked by the 250 reserve rule;
- CANARY readiness does not require a previous canary;
- SCHEDULED_COLLECTION readiness does require a recent successful canary;
- scheduled collection already being enabled is itself a pre-activation gate failure;
- passed canary facts require archive + database evidence;
- PostgreSQL migration/view/canary/gate persistence works end to end;
- lifecycle provider calls reduce broad odds capacity.

### CI and configuration

Updated Railway runtime smoke coverage for all Package E modules/tests.

Updated `.env.example` with the new budget, canary and gate controls.

### Current production decision

Scheduled collection remains **OFF**.

The next step is CI validation of this branch. Only after Package E is green and deployed should a bounded canary be considered.


## CI iteration 1 — formatter failure and correction

PR #9 was opened for Package E.

Initial global `Baseball tests` run:

- workflow run: `36154351534`;
- compile step: SUCCESS;
- failure step: `ruff format --check .`;
- lint and pytest did not run because formatting failed.

Ruff identified exactly two unformatted files:

1. `src/quantbot/baseball/activation_gate.py`
   - compacted five simple `int(os.getenv(...))` assignments;
2. `tests/test_durable_collector.py`
   - reformatted the three multiline `assert remaining_broad_odds_capacity(...) == value` expressions.

Corrections were applied in commits:

- `c1ce416` — activation gate Ruff formatting;
- `239110c` — budget test Ruff formatting.

This was a formatting-only failure. Python compilation had already succeeded.

No production configuration changed. Collection remains disabled.


## CI iteration 2 — lint failure and correction

Second global `Baseball tests` run:

- workflow run: `36154509287`;
- compile: SUCCESS;
- Ruff format: SUCCESS;
- Ruff lint: FAILED;
- pytest did not run.

Exact lint findings:

- `src/quantbot/baseball/canary.py:141` — BLE001 broad `except Exception as exc`;
- `src/quantbot/baseball/canary.py:162` — BLE001 broad inner `except Exception`.

Correction:

- operational failure handling now catches only:
  - `RuntimeError`;
  - `ValueError`;
  - `psycopg.Error`;
- unexpected programmer errors such as `AttributeError`, `KeyError`, or unrelated `TypeError` are no longer converted into a generic failed-canary fact;
- failed-canary persistence fallback catches only `psycopg.Error`; if failure evidence itself cannot be persisted because PostgreSQL is unavailable, the original operational exception is re-raised.

Fix commit:

- `0b705da` — narrow canary operational exception handling.

This correction improves observability rather than merely satisfying lint: coding defects now surface instead of being silently classified as provider/runtime canary failures.

Production collection remains disabled and no production canary has been executed.


## CI iteration 3 — Package E code gates green

Package E code head before this documentation-only update:

- `2129cf441153e570aba5a069d258a874ce35fde9`.

Verification:

- `Baseball tests` workflow run `36154788452`: **SUCCESS**;
- `Railway runtime smoke` workflow run `36154788449`: **SUCCESS**.

Railway smoke job `108136579056` passed every required step:

- PostgreSQL container startup;
- checkout/setup;
- dependency installation;
- Python compile;
- focused Ruff formatting;
- focused Ruff lint;
- focused pytest including Package E PostgreSQL integration;
- clean container shutdown.

Therefore the Package E implementation has passed both global repository validation and PostgreSQL-backed runtime validation.

### Package E merge readiness

The implementation is now code-ready for merge.

Still intentionally **not performed**:

- no production canary execution;
- no `BASEBALL_ENABLE_CANARY` variable change;
- no `BASEBALL_ENABLE_COLLECTION` variable change;
- no scheduled production collection activation.

Post-merge sequence remains:

1. verify Railway deploy of Package E;
2. verify migration `007_operational_acceptance.sql` is applied in production;
3. run the deployed `CANARY` activation assessment while collection remains OFF;
4. document the exact READY/BLOCKED result;
5. only if CANARY readiness is READY, separately decide whether to arm and execute one bounded canary;
6. scheduled collection remains OFF until the canary passes and the `SCHEDULED_COLLECTION` gate is READY.


## Production deployment and gate reachability follow-up

Package E PR #9 merged to main as:

- `d1e7b82f5006507200f6f9ebe652e60533455538`.

Baseball Railway auto-deployment:

- project: `believable-contentment`;
- service: `quantbet-baseball`;
- deployment: `26d1ed34-70d7-4aaa-a23f-e0452ac35133`;
- deployment status: **SUCCESS**;
- deploy log explicitly confirmed:
  - `007_operational_acceptance.sql` applied.

Scheduled collection was not enabled by the deploy.

### Production prerequisite audit

A read-only Railway variable-name audit confirmed:

Present:

- `DATABASE_URL`;
- `PAPER_MODE`;
- `BASEBALL_ENABLE_COLLECTION`;
- complete raw archive variable set;
- API base URL / retry / daily budget variables.

Missing:

- `API_BASEBALL_KEY`.

No alternate Baseball provider-key variable name was found.

Therefore the production CANARY readiness verdict is expected to include:

- `API_KEY_MISSING`.

No secret values were exposed and no Railway variable was changed.

### Operational reachability gap

The Package E activation gate was originally exposed as:

```text
PYTHONPATH=src python -m quantbot.baseball.activation_gate
```

Railway's available management interface does not provide arbitrary `exec` into an already deployed cron container.

A Railway agent check confirmed:

- no direct arbitrary command execution surface;
- no direct SQL execution surface;
- executing the CLI would otherwise require a temporary service/config change.

Decision:

> Do not create a temporary production function or mutate service configuration merely to invoke the readiness gate.

### Runtime gate hotfix

Created branch:

- `package-e-gate-runtime-20260925`.

Implemented:

- storage-ready worker automatically executes the `CANARY` readiness assessment whenever:
  - scheduled collection is OFF; and
  - `DATABASE_URL` exists;
- assessment is persisted through the existing immutable `activation_gate_assessments` table;
- no provider API request is made by the gate;
- worker JSON logs only a compact activation projection:
  - assessment ID;
  - target;
  - verdict;
  - reason codes;
  - budget;
  - checks;
- full performance diagnostics remain queryable from PostgreSQL views and are not duplicated into every cron log;
- when collection is ON, the storage-ready gate is not executed.

Hotfix commits so far:

- `787fa56` — emit CANARY readiness from storage-ready worker;
- `2a1c498` — test storage-ready activation gate emission.

Expected production behavior after hotfix deploy:

```text
collection_enabled=false
mode=storage-ready
activation_gate.verdict=BLOCKED
activation_gate.reason_codes includes API_KEY_MISSING
```

This closes the operational gap without enabling collection, enabling canary, adding an HTTP admin endpoint, or modifying Railway service configuration.


## Gate runtime hotfix CI — green

Hotfix PR #10 code/doc head before this final documentation commit:

- `5a135926f5bf56f91213c5a6aefcae0d74c6d8dc`.

Verification:

- global `Baseball tests` run `36155704541`: **SUCCESS**;
- `Railway runtime smoke` run `36155704549`: **SUCCESS**.

The PostgreSQL smoke passed:

- compile;
- focused Ruff format;
- focused Ruff lint;
- focused tests including runtime foundation and operational acceptance database tests.

The hotfix is merge-ready from a code/database perspective.

Expected production verification after merge:

1. Railway deploy succeeds;
2. migration state remains current;
3. next storage-ready cron persists an activation assessment;
4. worker log exposes compact `activation_gate`;
5. expected verdict is `BLOCKED`;
6. expected reason set includes `API_KEY_MISSING`;
7. `collection_enabled` remains `false`.


## Production configuration drift correction

Live storage-ready gate output after the runtime hotfix proved the gate is reachable and persisted.

Observed production assessment:

- verdict: `BLOCKED`;
- reasons:
  - `API_BUDGET_UNSAFE`;
  - `API_KEY_MISSING`.

The budget blocker was traced to Railway configuration drift:

- `BASEBALL_API_REQUEST_BUDGET=78`.

This value was historical per-run configuration. Package E now interprets the variable as the provider daily subscription ceiling.

The repository contract and Package E budget design use:

- daily ceiling: `7500`;
- per-cycle hard cap: `75`;
- 96 cycles/day;
- worst-case: `7200`;
- reserve requirement: `250`;
- theoretical safe headroom: `300`.

Production correction applied:

- `BASEBALL_API_REQUEST_BUDGET=7500`.

Railway deployment triggered by the variable change:

- `ea40064f-a02c-4228-9d1f-5792402e48e2`.

At the time of writing it was still initializing.

No API key was added, no canary was armed, and scheduled collection remains OFF.

The expected next readiness state is `BLOCKED` only by `API_KEY_MISSING`, pending verification from the redeployed worker log.


## Budget-fix redeploy result

The Railway deployment caused by the `BASEBALL_API_REQUEST_BUDGET=7500` correction completed successfully:

- deployment: `ea40064f-a02c-4228-9d1f-5792402e48e2`;
- status: `SUCCESS`;
- deployed commit remains `fdaf67048ac776a31774421c0f9fe31987890e8b`;
- no new migration was required.

Important cron behavior:

- deployment startup/pre-deploy is not the scheduled worker execution;
- the redeploy therefore did not immediately emit a fresh activation assessment.

Railway was checked for a safe manual cron trigger. No non-mutating one-shot invocation is available.

Decision:

> Preserve production configuration and wait for the normal 15-minute cron instead of temporarily changing cron/service behavior merely to force the gate.

Expected next live assessment remains:

- budget safe at 7,500 daily ceiling / 7,200 worst-case;
- `API_BUDGET_UNSAFE` absent;
- `API_KEY_MISSING` present;
- verdict `BLOCKED`;
- collection OFF.

This remains an expectation until the scheduled worker log confirms it.


## Post-budget-fix scheduled execution acceptance — 2026-09-25

The outstanding Package E production expectation has now been verified from a **real natural Railway cron execution**, without changing cron, service behavior, collection state, or canary state.

### Deployment state

Current Baseball production deployment:

- `1466ff80-d238-4f38-9822-c4098fafc9da`;
- source commit: `cc31a5dc0cfa525d4bccac7b90ea247cb94d1ae6`;
- final status: **SUCCESS**.

This docs-only deployment superseded the earlier budget-variable redeployment while preserving the corrected production variable state. The service remains scheduled at:

- `*/15 * * * *`.

Railway service config still has no watch patterns configured. No further attempt was made to modify them.

### First natural cron proving the corrected budget

First observed scheduled worker execution after the budget correction:

- start: `2026-09-25T16:15:46.860128915Z`;
- structured runtime/gate record: `2026-09-25T16:15:48.524278955Z`;
- assessment ID: `93f7b3b6-c297-52ed-8ddb-ba31c5688bd1`.

Exact activation-gate budget projection:

```text
daily_request_budget=7500
cycle_request_cap=75
cycles_per_day=96
worst_case_daily_requests=7200
request_headroom=300
daily_reserve_required=250
```

Exact relevant checks:

```text
api_key_configured=false
canary_passed=false
collection_enabled=false
migrations_current=true
paper_mode=true
raw_archive_configured=true
runtime_fresh=true
```

Result:

```text
target=CANARY
reason_codes=[API_KEY_MISSING]
verdict=BLOCKED
mode=storage-ready
```

This proves the production budget drift is fully resolved:

- `API_BUDGET_UNSAFE` no longer appears;
- the 7,500 daily ceiling is being interpreted correctly;
- the collector remains capped at 75 fresh attempts per cycle;
- worst-case daily usage remains 7,200;
- theoretical headroom remains 300, above the required 250 reserve.

### Repeated-run confirmation

A later natural run at `2026-09-25T21:15:17.162099029Z` produced the same gate state with assessment:

- `870a6ef0-fcbf-5a06-a5dc-cc760a8c8a74`;
- only blocker: `API_KEY_MISSING`;
- verdict: `BLOCKED`;
- `collection_enabled=false`.

### Package E acceptance boundary

Package E operational acceptance has reached the credential boundary.

No code defect, migration defect, budget defect, runtime freshness defect, archive configuration defect, or paper-mode defect is blocking the CANARY target.

The remaining blocker is exactly:

- missing Railway variable `API_BASEBALL_KEY`.

Until that credential exists:

- do not enable `BASEBALL_ENABLE_CANARY`;
- do not enable `BASEBALL_ENABLE_COLLECTION`;
- do not fabricate provider evidence;
- keep production in `PAPER_MODE=true`.


## Handoff revalidation — 2026-09-26

A fresh read-only production check reconfirmed the Package E acceptance boundary.

Current production deployment:

- `1466ff80-d238-4f38-9822-c4098fafc9da`;
- status: **SUCCESS**;
- source commit: `cc31a5dc0cfa525d4bccac7b90ea247cb94d1ae6`;
- cron: `*/15 * * * *`.

Current service config still contains no watch-pattern restriction, and the production
variable-name inventory still does not contain `API_BASEBALL_KEY`.

Latest completed natural cron inspected:

- gate timestamp: `2026-09-25T22:00:51.824842688Z`;
- assessment ID: `f940b8d9-0240-5269-b0be-5ebf532de2e7`;
- `daily_request_budget=7500`;
- `cycle_request_cap=75`;
- `worst_case_daily_requests=7200`;
- `request_headroom=300`;
- `reason_codes=[API_KEY_MISSING]`;
- `collection_enabled=false`;
- `paper_mode=true`;
- verdict: **`BLOCKED`**.

This independently reconfirms that the budget blocker is resolved and the remaining
production blocker is solely the absent provider credential.

No canary, collection activation, watch-pattern mutation, cron mutation, redeploy, or PR merge was performed.


## Provider-key handoff check — 2026-09-26

The operator reported adding `API_BASEBALL_KEY`.

Immediate production verification found:

- new deployment `59cccc85-cc41-45aa-8b46-9760c3945cd6` entered `BUILDING`;
- guarded service/environment are correct;
- the Railway variable inventory exposed to `quantbet-baseball` still does not list `API_BASEBALL_KEY`.

Safety response:

- no canary arming;
- no collection activation;
- no cron/config mutation;
- wait for the deployment/variable state to become independently observable, then require the CANARY activation gate to become ready before any bounded provider request is allowed.


## Provider URL restoration after credential misplacement — 2026-09-26

A credential-entry mistake was identified: the provider key had been placed in `API_BASEBALL_BASE_URL`.

The canonical URL was independently verified from `config.py` and `.env.example`:

- `https://v1.baseball.api-sports.io`.

Production repair:

- restored `API_BASEBALL_BASE_URL` to the canonical URL;
- skipped redeploy for this repair;
- left collection and canary disabled;
- no credential was fabricated or copied.

Remaining blocker: create `API_BASEBALL_KEY` on the guarded Baseball production service using the real provider secret.


## Provider credential visibility confirmed — 2026-09-26

Railway now exposes `API_BASEBALL_KEY` to the guarded Baseball production service. A new deployment, `667487c1-6b31-4624-ae36-a655147b6f08`, was created by the credential change and was initially `WAITING`.

No canary or scheduled collection activation was performed. The next acceptance requirement is a natural storage-ready gate proving CANARY readiness with the key configured.


## Credential deployment success; natural CANARY gate pending — 2026-09-26

The credential-triggered deployment `667487c1-6b31-4624-ae36-a655147b6f08` completed with **SUCCESS**. No migration was newly applied during pre-deploy.

The API key is now visible to the correct Baseball service, but deployment startup is not being treated as a readiness substitute. No canary or scheduled collection was enabled. The next accepted proof is the first natural `*/15` storage-ready worker execution on this deployment.

A one-time follow-up verification is scheduled for the next cron window; it must only proceed toward bounded canary execution if the natural CANARY activation gate is ready and a safe existing one-shot execution path is available.


## Natural CANARY gate READY and next execution design — 2026-09-26

Natural cron executions on deployment `667487c1-6b31-4624-ae36-a655147b6f08` now prove the CANARY gate is `READY` with no blocker codes. The live budget projection remains 7500 daily / 75 per scheduled cycle / 7200 worst-case / 300 headroom, and production remains `PAPER_MODE=true`, `BASEBALL_ENABLE_COLLECTION=false`.

The chosen safe execution mechanism is a DB-idempotent one-shot path inside the existing worker: an explicit canary flag may trigger one bounded canary only when the CANARY gate is READY; once a recent PASSED canary exists, later cron invocations must skip re-execution even if the flag remains armed. No cron rewrite, start-command rewrite, temporary service, or collection enablement is required.


## One-shot canary implementation and arming — 2026-09-26

PR #14 introduced the safe one-shot execution mechanism required to run the existing bounded canary without temporary cron/start-command/service hacks. CI passed and the PR was squash-merged to main as `dd423761e9146c1ea674a483ae8b12c3fe84fc50`. Deployment `26d1fbdd-7389-4ad4-b9b4-691aefcb2fcb` reached SUCCESS.

The guarded Baseball service was then armed with explicit caps: 8 total provider attempts, 2 odds requests, 1 monitoring refresh, and 1 settlement refresh. `BASEBALL_ENABLE_COLLECTION=false` and `PAPER_MODE=true` were explicitly reasserted. Railway created redeployment `b7c0a7ea-5a76-464e-8efe-81187b3a3634`.

Acceptance remains pending the natural cron evidence. PASS is not assumed in advance.


## First bounded provider canary result — FAILED safely — 2026-09-26

Natural cron executed the one-shot canary at `2026-09-25T23:16:05.657939242Z`.

Observed evidence:

- `status=FAILED`;
- 4 provider requests, bounded below the cap of 8;
- 66 games/fixtures seen and 66 fixture observations persisted;
- 2 odds calls returned 1387 raw market rows;
- 0 canonical odds observations were produced or inserted;
- no provider/collector errors;
- archive/db verification therefore remained false;
- failure reasons: `POSTGRES_WRITES_NOT_VERIFIED`, `RAW_ARCHIVE_NOT_VERIFIED`.

Interpretation: provider connectivity and fixture persistence are proven. Live odds payload mapping is not. Collection remains disabled and no activation claim is made. Next action is to diagnose the real provider odds shape against the canonical mapper, repair with regression fixtures/tests, deploy, and rerun one bounded canary.


## Failed canary disarmed and live odds mapper repair opened — 2026-09-26

The failed canary was immediately disarmed to avoid re-running provider requests every 15 minutes. Deployment `2c42711f-e4b2-4410-a05f-407cdb767113` succeeded with canary and scheduled collection disabled and paper mode retained.

PR #15 repairs the observed live-moneyline mapping boundary by admitting API-Sports `Home/Away` as a full-game two-way moneyline alias, removes legacy player-prop target tokens from compact game-line processing, and adds bounded live market-name diagnostics. Full raw payload archiving remains unchanged.


## First live canary result: safe failure in canonical odds ingestion — 2026-09-26

The first natural bounded canary executed at `2026-09-25T23:16:05.657939242Z` and failed closed. It used 4/8 allowed provider attempts with 0 API errors, inserted 66 fixture observations, made 2 odds calls and observed 1387 compact market value rows, but produced 0 canonical odds rows and 0 PostgreSQL odds observations. Canary id: `e52931fc-e7ab-56cc-be44-9f175c20f1e8`; collection cycle: `dbddfcb8-6a6f-412b-b46a-017b986286f3`.

Reason codes were `POSTGRES_WRITES_NOT_VERIFIED` and `RAW_ARCHIVE_NOT_VERIFIED`. This localizes the acceptance failure to odds canonicalization rather than provider connectivity or fixture storage.

The canary flag was immediately disarmed after the failed run, with collection kept false and paper mode true. Deployment `2c42711f-e4b2-4410-a05f-407cdb767113` now represents that safe state.


## Canary-only odds schema probe merged — 2026-09-26

PR #16 added a diagnostic-only extension to the bounded canary path. It exposes distinct provider market names and selection labels while excluding odds values and credentials. CI initially caught formatting drift; no merge occurred until it was fixed. Final Baseball tests and Railway runtime smoke both passed. The PR was squash-merged as `e0f2926287c4dd269a499249f3645f684e2d048a`.

This change does not widen the full-game moneyline parser. A second bounded canary is required to obtain exact live provider naming before the parser is changed.


## Canary schema probe re-armed — 2026-09-26

The canary-only schema probe is now on main as `e0f2926287c4dd269a499249f3645f684e2d048a`; deployment `d60fd5df-7b4d-495d-8255-aa2eb19edee7` is SUCCESS. One bounded diagnostic canary was re-armed with the existing 8/2/1/1 caps while collection remains false and paper mode remains true. No parser widening is authorized until the natural canary returns the exact live market/selection schema.


## Second bounded schema-diagnostic canary — 2026-09-26

Schema-probe commit `e0f2926287c4dd269a499249f3645f684e2d048a` deployed successfully. The diagnostic canary was re-armed with caps 8/2/1/1 while `BASEBALL_ENABLE_COLLECTION=false` and `PAPER_MODE=true`. Redeployment `d60fd5df-7b4d-495d-8255-aa2eb19edee7` reached SUCCESS. Acceptance remains pending the next natural cron; no market-name hypothesis is treated as proven before that evidence is emitted.


## Second bounded canary diagnostic result — 2026-09-26

The schema-probe canary ran naturally at `2026-09-25T23:46:33.726660077Z` (canary `e7e10245-4941-55c1-8cdd-f7b662047dca`, cycle `eaf76e67-fea3-42e3-90ee-b40f8dddb488`). It used 4/8 provider requests with zero API errors, inserted 66 fixture observations, but the two selected odds calls produced 0 compact market rows and therefore 0 canonical/PostgreSQL odds observations. Both schema-name diagnostic fields were empty.

No parser widening is justified by this run. Canary was disarmed again and collection remains disabled. The next probe will distinguish an empty odds response from an unrecognized response shape and may inspect up to four games under the same 8-request ceiling.


## Moneyline canonicalization root cause and fix — 2026-09-26

Live-history payloads in the repository proved that API-Sports Baseball market id `1` is `Home/Away` with exactly `Home` and `Away`, while market id `14` `Match Winner` is three-way (`Home/Draw/Away`). The prior canonicalizer omitted the first market and could incorrectly drop `Draw` from the second.

PR #22 fixed both behaviors and passed Baseball tests plus Railway runtime smoke before merging to main as `a4d20a9d624342a286603fe46bd2a4cf3dff3640`.

No collection activation occurred. Next requirement: deploy this commit and run one bounded canary with <=8 total provider attempts and <=4 broad odds calls.


## Third bounded canary after Home/Away fix — 2026-09-26

Deployment `b57c3196-98f1-48ef-9c63-65666ed9c264` successfully ran main commit `a4d20a9d624342a286603fe46bd2a4cf3dff3640`. The next natural cron executed bounded canary `6f337f6f-d35a-595d-9874-f5d909a5dca0` (cycle `88839d4c-7b40-4fe6-b3e4-c4d132339c19`). It used 6/8 provider requests and selected 4 games for odds, but all four odds responses were empty: 0 payload rows, 0 bookmaker records, 0 raw market rows, 0 canonical rows, 0 PostgreSQL odds observations, and 0 API errors.

This canary therefore failed with `POSTGRES_WRITES_NOT_VERIFIED` and `RAW_ARCHIVE_NOT_VERIFIED`. It did not invalidate the Home/Away parser fix because no market payload reached the parser. Canary was disarmed again, collection remains disabled, and paper mode remains true.


## Live one-request /games schema audit completed — 2026-09-26

The guarded Baseball service completed audit `games-schema-live-20260926-1` using exactly one provider request to `/games?date=2026-09-26`. It returned 35 games: MLB 16, NPB 5, Asian Games 4, CPBL 3, KBO 3, Elitserien 2, Bundesliga 1, Division 1 1. MLB and sampled non-MLB rows exposed the same schedule/status schema and no injuries, pitchers, lineups, players, venue/stadium, roof, umpire, or weather fields. Raw payload archival succeeded. A later cron returned `ALREADY_DONE` with zero requests, proving one-shot idempotence. Audit flags were cleared; collection and canary remain off; paper mode remains on.
