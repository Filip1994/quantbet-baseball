# Legacy Porting Matrix — `Filip1994/h2h` to Baseball

**Status:** Preliminary; component-level review pending.

| Legacy area | Initial disposition | Baseball decision rule |
|---|---|---|
| Dixon–Coles scoring logic | ADAPT / QUARANTINE | Reuse only the statistical concepts that fit baseball run scoring; validate against baseball data and avoid assuming football goal-process assumptions transfer unchanged. |
| Calibration utilities | ADAPT | Potentially reusable if independent of football outcome semantics; require reliability, Brier, log-loss, and time-split tests. |
| Closing/market comparison logic | ADAPT | Reuse only domain-neutral price, timestamp, and market-lineage concepts. Rebuild market taxonomy for baseball. |
| Bookmaker registry | ADAPT | Reuse provider abstraction ideas; rebuild supported providers, markets, rate limits, and baseball selection mappings. |
| Settlement logic | ADAPT | Rebuild around baseball game completion, postponed/suspended games, extra innings, two-way moneyline rules, and void conditions. |
| Football API modules | REJECT for direct use | Do not port football endpoints, schemas, or assumptions into baseball. |
| Prediction artifacts | QUARANTINE | Treat as historical evidence only until provenance, leakage, and reproducibility are proven. |
| Health/quota/coverage artifacts | ADAPT | Rebuild as explicit operational metrics with tests and Railway-compatible persistence. |
| Dashboard/UI assets | QUARANTINE | Consider visual concepts only after backend contracts are stable. |
| JSON/JSONL operational stores | REJECT as operational source of truth | Migrate concepts to PostgreSQL and immutable raw evidence storage; retain archives only as evidence. |

## Review protocol

For each candidate component, record:

1. file path and public interfaces;
2. mathematical or operational purpose;
3. hidden domain assumptions;
4. test coverage;
5. data dependencies;
6. security and reliability concerns;
7. proposed baseball replacement or adaptation;
8. decision and approving commit.

## Current conclusion

The legacy repository may contain useful engineering patterns and mathematical utilities, but the baseball project must remain independently testable. No legacy component is approved for direct production use by this preliminary audit.
