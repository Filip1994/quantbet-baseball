# QuantBet Baseball

Standalone Baseball data, modelling and paper-trading engine for QuantBet.

## Current architecture

- **Observe first:** event universe is discovered independently from betting qualification.
- **Adaptive observation lifecycle:** cadence increases as first pitch approaches; the 15-minute workflow clock is the production upper bound.
- **Canonical evidence:** every retained bookmaker / market / selection observation is written to `data/baseball/market_observations.jsonl` with event identity, capture time, source and validation metadata.
- **Raw evidence:** uncached API envelopes are archived under `data/baseball/raw_api/` for parser auditing.
- **Opening integrity:** opening price is only reported when an earlier observation actually exists; otherwise it remains unavailable.
- **Lifecycle states:** discovered → observing → modelled → eligible → signal → pick → closing → settled → evaluated, with explicit skip/block/error states and reason codes.
- **API economics:** 15-minute runs, 74 hard attempts/run and 72 odds slots produce a theoretical ceiling of 7,104 API attempts/day, leaving 396/day headroom below a 7,500/day subscription.
- **Presentation contract:** `data/baseball/dashboard.json` is the single frontend data contract; the website does not create a second betting truth.
- **Mobile-first control dashboard:** `docs/index.html` exposes overview, watchlist, production, signals, market intelligence and system health.
- **Paper-only operation:** no real-money staking.

## Baseball-specific modelling roadmap

The prediction model is intentionally not considered production-ready. The next stages are historical time-series construction, point-in-time feature engineering, Baseball-specific probability models, calibration, walk-forward validation, CLV capture and settlement.

Candidate features include starting pitcher and handedness, workload, bullpen availability, confirmed/expected lineup, batter/pitcher splits, park/weather, rest/travel, offense/defense and market state.

The initial supported market scope is deliberately constrained to:

- full-game moneyline;
- full-game totals with an explicit line, initially 8.5 and 9.5.

Run line, F5 markets, team totals, alternate lines, futures, parlays/SGPs, live betting, automated staking and **player props are out of scope** for this project phase. Market expansion requires separate evidence, settlement and validation work and is not implied by this repository.

## Operating philosophy

> **Observe first. Preserve evidence. Decide second. Evaluate third. Optimize last.**

Collection is deliberately broader than production qualification. A market observation is evidence, not a bet. Missing evidence is represented as unavailable rather than reconstructed or guessed.

## Safety

`PAPER_MODE=true` is the default. No real-money staking is performed by this repository.
