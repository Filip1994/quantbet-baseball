# QuantBet Baseball v1

Standalone Baseball engine for QuantBet.

## Current live-data phase

- API-Sports Baseball client at `https://v1.baseball.api-sports.io`
- persistent response cache
- per-run request budget and retry/backoff
- scheduled 30-minute Baseball ingestion during the active day
- up to 199 odds calls per run plus the daily schedule call
- league-diversity sampling so smaller leagues are not starved by MLB
- compact historical snapshots under `data/baseball/snapshots/`
- bookmaker and market coverage inventory under `data/baseball/market_coverage.json`
- Baseball intraday signal schema and paper alert layer

The first live payload must be used to audit actual bookmaker and market names before we claim coverage for any specific local bookmaker.

## Budget policy

The production subscription is 7,500 requests/day. The scheduled collector is capped at 200 requests per run and runs every 30 minutes from 06:00 through 23:30 Europe/Belgrade. That is 7,200 scheduled requests/day before retries; the remaining daily headroom is a safety reserve.

## Model direction

Baseball reuses the QuantBet operating pattern where structurally sound:

1. scheduled baseline screening;
2. persistent prediction and odds snapshots;
3. frequent intraday refreshes;
4. immutable signal timestamps;
5. CLV capture and settlement;
6. paper-first alerts;
7. production gating only after calibration and walk-forward validation.

The Baseball model is not a copy of the Football model. The feature surface will include starting pitcher, handedness, expected/confirmed lineup, batter/pitcher splits, bullpen availability and workload, park, weather, rest/travel, team offensive/defensive rates, market state and player-level features where the feed supports them.

## Market scope

Initial market classes:

- Moneyline / game winner
- Run line / spread
- Game total runs
- player props only after live coverage and settlement semantics are validated

## Entry Decision

The eventual Entry Decision Engine will evaluate each snapshot independently and may emit `WAIT`, `UPLATI SADA` or `SKIP`. An issued signal is never silently rewritten by later refreshes.

The initial implementation is paper-only. The learning target is the optimal information/market state for entry, rather than a hardcoded number of hours before first pitch.

## Next stages

1. Validate live odds payloads and bookmaker/market schemas.
2. Normalize games, teams, pitchers, lineups, player stats and odds.
3. Build Baseball probability/fair-odds models.
4. Add calibration and walk-forward evaluation.
5. Feed predictions into the intraday scanner and paper alert layer.
6. Add Baseball-specific ledger, CLV tracking and outcome settlement.
7. Learn the Entry Decision policy from the collected footprint.
