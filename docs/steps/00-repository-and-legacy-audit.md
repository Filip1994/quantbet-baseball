# Step 00 — Repository and Legacy Audit

**Status:** Started  
**Date:** 2026-09-14

## Scope

Audit `Filip1994/quantbet-baseball` as the target system and `Filip1994/h2h` as a read-only legacy reference.

## Initial findings

### Baseball repository

The repository already contains:

- `BASEBALL.md`
- `BASEBALL_PROGRESS.md`
- `README.md`
- `src/`, `tests/`, `scripts/`, and `docs/`
- GitHub Actions workflows for collection, training, and tests
- baseball data artifacts, raw API snapshots, market coverage, and market intelligence
- Python project metadata and dependency files

The repository therefore has an existing foundation, but the current state must be verified rather than assumed production-ready. Large data artifacts in Git require special attention before Railway migration.

### Legacy repository

`Filip1994/h2h` contains a broader and more operationally complex system, including:

- calibration and closing logic;
- bookmaker registry and API integrations;
- football-specific API code;
- prediction, settlement, health, quota, and coverage artifacts;
- dashboard/UI assets;
- historical JSON/JSONL operational data.

The legacy repository is not a trustworthy production baseline. It is a source of ideas and possible isolated components only. Its Dixon–Coles-related logic may be mathematically useful for appropriate scoring models, but it must not be transplanted without tests, domain review, and baseball adaptation.

## Audit classification rules

Each legacy component will be classified as:

- **REUSE:** domain-neutral, tested, and safe to port;
- **ADAPT:** useful concept but requires baseball-specific redesign;
- **QUARANTINE:** potentially useful but insufficiently tested or coupled;
- **REJECT:** broken, obsolete, unsafe, or incompatible.

## Required next inspection

1. Read all baseball source modules and tests.
2. Read collection/training/test workflows.
3. Inspect current dependency and configuration assumptions.
4. Inspect legacy mathematical modules, especially Dixon–Coles, calibration, bookmaker registry, settlement, and closing logic.
5. Build a component-by-component porting matrix.
6. Record all findings in `docs/LEGACY_PORTING_MATRIX.md`.

## Safety constraints

- Do not merge legacy code directly.
- Do not delete existing data.
- Do not overwrite Railway production resources.
- Do not call a model production-ready based on file presence alone.
