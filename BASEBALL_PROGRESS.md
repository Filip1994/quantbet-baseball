

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
- `7bc82c6` — expanded market snapshot contract tests.

Test execution has not been independently confirmed in a local runtime.
