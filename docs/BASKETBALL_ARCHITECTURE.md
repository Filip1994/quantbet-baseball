# QuantBet Basketball

## Pilot scope

Pregame only. Paper only.

### Eligible bookmakers
- 1xBet
- Bet365

### Primary markets
- 1st Half Total (market 5)
- 1st Quarter Total (market 16)
- 2nd Quarter Total (market 45)
- 3rd Quarter Total (market 46)

### Benchmark
- Full Game Total (market 4)

### Explicit exclusions
- Q4 totals
- live/in-play analysis
- spreads
- moneyline
- player props

## Eligibility gate
A game/league is eligible only when historical quarter scoring, team statistics, pregame odds, and at least one allowed bookmaker quote are available for the target period market.

## Research principle
Q1/Q2/Q3 and 1H are modeled separately. Q2/Q3 edge is a hypothesis to test, not a hard-coded assumption. FT is retained as a benchmark/control market.

## Deployment principle
Low-compute scheduled execution only. No persistent polling or live feed.
