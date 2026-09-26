# QuantBet Baseball Data Source Architecture

**Status:** canonical source hierarchy  
**Effective:** 2026-09-26

## 1. Governing hierarchy

```text
API-Sports Baseball = PRIMARY PROVIDER
MLB Stats API       = ENRICHMENT ONLY
Open-Meteo          = WEATHER ONLY
QuantBet            = LOCAL DERIVATIONS + MODELS
```

The system captures provider evidence broadly but models selectively.

> If a datum can be cached or derived locally, do not spend another provider request on it.

## 2. API-Sports Baseball — primary provider

API-Sports is canonical for:

- games, schedules and historical games;
- game status and results;
- leagues, seasons and team identity;
- standings;
- team statistics and home/away splits;
- odds;
- bookmakers;
- betting-market catalog;
- market movement and consensus;
- final result / settlement evidence.

### Games

Canonical source facts:

- provider game ID;
- scheduled first pitch;
- provider timezone;
- status;
- league ID;
- season;
- home/away team IDs;
- final scores for result/settlement only.

Current-game final scores never become pregame model features.

### Standings

Canonical source facts include:

- games played;
- wins/losses;
- win/loss percentages;
- runs scored/allowed;
- standings position;
- group/stage;
- team/league identity.

Derived locally:

- run differential;
- runs/game;
- runs allowed/game.

### Team statistics

The verified `teams/statistics` object is the canonical team-strength source.

Retain overall/home/away:

- sample sizes;
- W/L counts and percentages;
- runs scored totals/averages;
- runs allowed totals/averages.

Model-facing compact representations should prefer rates plus sample size. Do not blindly feed algebraically redundant wins, losses, win%, loss% and games as independent signals.

### Odds and books

Executable books are hard-locked to:

- API-Sports bookmaker ID **1 — 1xBet**;
- API-Sports bookmaker ID **2 — Bet365**.

Other books are intelligence-only and may support:

- de-vigged consensus probability;
- median price;
- dispersion;
- stale/outlier detection;
- movement;
- executable-book vs consensus comparison;
- closing-line evaluation and CLV.

They may never become registered executable quotes.

### Markets

Current production market:

- full-game Home/Away Moneyline.

Next market:

- full-game Over/Under with explicit line identity.

Catalog presence is identity evidence only. It does not prove game/book coverage.

Player props remain OFF.

## 3. MLB Stats API — enrichment only

MLB Stats API must not become a second canonical source for API-Sports schedule, standings, team strength, results or betting markets.

Permitted enrichment:

- probable/confirmed starter identity and state;
- starter changes/scratches;
- lineup order and lineup state;
- active roster;
- transactions;
- bullpen usage/workload;
- venue, coordinates, field orientation, roof metadata and timezone.

MLB schedule access is allowed only as an identity bridge to obtain `gamePk` needed for granular enrichment. The API-Sports fixture remains the canonical game.

Historical MLB `timecode` replay must use the returned `metaData.timeStamp` as the source cutoff. Requested timecode is not sufficient anti-leakage evidence.

Expected and confirmed lineups must remain distinct states.

## 4. Open-Meteo — weather only

Use only for:

- temperature;
- humidity;
- dew point;
- surface pressure;
- precipitation probability/amount;
- cloud cover;
- wind speed/direction/gusts;
- weather code.

Derive locally:

- air-density proxy;
- outward/inward wind component once field orientation is known;
- park × weather interactions;
- delay/rain proxy;
- day/night/twilight context.

Do not apply outside weather to a fixed dome or verified closed retractable roof.

For historical model work, archive and use the forecast available at the prediction cutoff; do not substitute final observed weather.

## 5. Local QuantBet derivations

Derive without additional provider requests whenever source evidence already exists.

From API-Sports game history:

- days/hours rest;
- schedule density;
- back-to-back;
- doubleheader;
- prior extra-inning context;
- recent game counts;
- home/road sequence;
- series context.

After venue registry exists:

- travel distance;
- timezone change;
- east/west travel;
- road-trip/homestand length;
- local first-pitch hour;
- circadian/body-clock proxy.

## 6. Refresh policy

| Source | Default cadence |
|---|---|
| live odds | adaptive/game-sensitive |
| game discovery/result monitoring | scheduled/due-driven |
| standings | daily |
| team statistics | daily / after completed-game window |
| bookmaker catalog | weekly or provider change |
| bet-type catalog | weekly or provider change |
| leagues/seasons/teams/static metadata | cached/versioned |
| MLB enrichment | point-in-time and game-sensitive, only where granular value exists |
| weather | prediction-window forecast snapshots |

Slow/static data must never consume budget ahead of settlement, registered-pick monitoring, executable quotes or due pregame odds.

## 7. Evidence pipeline

```text
PROVIDER RESPONSE
      ↓
IMMUTABLE RAW ARCHIVE
      ↓
CANONICAL SOURCE EVIDENCE
      ↓
LOCAL DERIVATIONS
      ↓
IMMUTABLE FEATURE SNAPSHOT
      ↓
MODEL
      ↓
PICK / PASS
```

Every prediction must be reproducible from archived evidence.

Minimum feature-snapshot invariant:

`source_data_cutoff_at <= predicted_at < first_pitch`

## 8. Product boundaries

- PAPER_MODE = ON
- REAL MONEY = OFF
- fixed paper stake = 300 RSD
- singles only
- executable books = Bet365 / 1xBet
- current market = full-game Moneyline
- next market = full-game Over/Under
- player props = OFF

## 9. Development order

1. maximize and canonicalize API-Sports primary-provider data;
2. finish local schedule/team-strength derivations;
3. add MLB enrichment only for granular missing baseball information;
4. add weather after venue/roof identity is reliable;
5. assemble immutable feature snapshots;
6. train/calibrate Moneyline V1 chronologically;
7. emit genuine PICK/PASS decisions;
8. close 300 RSD paper lifecycles through settlement + CLV;
9. only then activate full-game totals.

The system should use **maximum useful evidence**, not maximum feature dimensionality.
