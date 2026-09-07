# QuantBet Baseball

Standalone Baseball data, modelling and paper-trading engine for QuantBet.

## Current phase

- API-Sports Baseball ingestion
- persistent response cache
- bounded API request budget and retry/backoff
- 30-minute scheduled snapshots during the active day
- bookmaker and market coverage inventory
- intraday paper-signal plumbing
- paper-only operation

The prediction model is intentionally not considered production-ready yet. The next stages are live schema validation, feature normalization, Baseball-specific probability models, calibration, walk-forward validation, CLV capture and settlement.

## Architecture

Baseball follows the proven QuantBet operating pattern where appropriate, but uses Baseball-specific modelling features such as starting pitcher, handedness, lineup, batter/pitcher splits, bullpen workload, park, weather, rest/travel, team rates and market state.

Entry decisions will eventually be `WAIT`, `UPLATI SADA` or `SKIP`. Signals are immutable once issued.

## Safety

`PAPER_MODE=true` is the default. No real-money staking is performed by this repository.
