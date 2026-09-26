# QuantBet Baseball Variable & Market Registry

**Status:** canonical research-data registry  
**Last verified:** 2026-09-26  
**Primary product:** game-level paper betting research  
**Playable bookmakers:** **1xBet (API-Sports id 1)** and **Bet365 (API-Sports id 2)** only  
**Player props:** excluded from the product

This document defines which provider/external variables are retained, which are eligible for modeling, which betting markets are allowed, and how often each source may be refreshed.

Canonical source hierarchy is defined in `docs/DATA_SOURCE_ARCHITECTURE.md`: API-Sports is the primary provider, MLB Stats API is granular baseball enrichment only, Open-Meteo is weather only, and QuantBet derives locally wherever possible.

The governing rule is:

> Capture broad evidence, model only useful point-in-time-safe variables, and never spend API requests on data that can be cached, derived, or replayed from the raw archive.

## 1. Status vocabulary

- **ACTIVE** — approved as a canonical model/decision input once populated.
- **DERIVED** — computed from verified raw fields; no additional provider request.
- **DISPLAY_ONLY** — useful for UI/audit identity, not a model signal.
- **INTELLIGENCE_ONLY** — useful for market consensus/diagnostics but never an executable quote.
- **RAW_ONLY** — retained in immutable raw payloads but not canonicalized/modelled.
- **EXTERNAL_PENDING** — desired feature from a separate verified free source; not active until point-in-time ingestion exists.
- **REJECTED** — intentionally excluded because it is irrelevant, ambiguous, leaky, player-prop-only, or redundant noise.
- **UNVERIFIED** — code/docs may reference it, but production evidence has not proved the endpoint/field contract.

## 2. Live provider evidence used for this registry

On 2026-09-26 the guarded production service performed a bounded API-Sports Baseball surface audit.

Observed provider request count: **9**, hard cap **12**.

Successfully archived evidence included:

- MLB standings;
- NPB standings;
- MLB team statistics;
- NPB team statistics;
- odds bet-type catalog;
- bookmaker catalog.

A subsequent raw-archive inventory used **0 provider requests** and recovered the object-shaped team-statistics payloads that the old generic list parser could not interpret.

Live audit facts:

- /games?date=2026-09-26 returned 35 games across MLB and seven other competitions.
- /standings?league=1&season=2026 returned the MLB standings structure.
- /standings?league=2&season=2026 returned the same structural family for NPB.
- /teams/statistics?team=22&league=1&season=2026 returned a statistics object for MLB.
- /teams/statistics?team=58&league=2&season=2026 returned the same statistics structure for NPB.
- /odds/bets returned **83** catalog market definitions.
- /odds/bookmakers returned **30** bookmakers.
- /players returned provider error: **endpoint does not exist**.

The presence of a market in /odds/bets is a catalog fact only. It does **not** prove that the market is available for a given game, league, or bookmaker.

### Official MLB structured-source audit

A separate bounded public/no-auth audit of the official MLB Stats API also passed on 2026-09-26.

Verified live contracts:

- `/api/v1/schedule?sportId=1&date=2026-09-26&hydrate=probablePitcher,team,venue` returned 13 MLB games with structured team, probable-pitcher and venue identity;
- sampled game `822678` returned probable starter IDs/names for both clubs and venue ID/name;
- `/api/v1.1/game/{gamePk}/feed/live` exposed `gameData.probablePitchers`, `gameData.players`, venue/location/time-zone/field metadata and boxscore team structures including `battingOrder`, `bullpen`, `pitchers` and `players`;
- `/api/v1/teams/{teamId}/roster?rosterType=active&date=...` returned active-roster rows with person, position and status identity;
- `/api/v1/transactions` returned dated transaction rows with person/team/type/description fields.

Historical replay was also verified with `timecode` on a completed 2026-09-20 game. A requested snapshot roughly two hours before first pitch returned `Pre-Game` state, both probable pitchers and populated 9-player batting orders for both clubs.

Critical point-in-time rule: the requested `timecode` is **not** the authoritative cutoff. In the bounded audit, requested `20260920_151000` returned `metaData.timeStamp=20260920_151258`. Historical ingestion must persist the response metadata timestamp and may use the snapshot only when that actual response timestamp is at or before the model prediction cutoff.

# 3. API-Sports /games

## 3.1 Raw fields observed

- id
- date
- time
- timestamp
- timezone
- week
- status.long
- status.short
- country.id
- country.name
- country.code
- country.flag
- league.id
- league.name
- league.type
- league.logo
- league.season
- teams.home.id
- teams.home.name
- teams.home.logo
- teams.away.id
- teams.away.name
- teams.away.logo
- scores.home
- scores.away

The same top-level schema was observed for MLB, NPB and sampled non-MLB competitions.

## 3.2 Canonical/useful variables

| Canonical variable | Source field | Status | Use |
|---|---|---|---|
| provider_game_id | id | ACTIVE | fixture identity |
| scheduled_first_pitch | date / timestamp | ACTIVE | cutoff, rest, scheduling |
| provider_timezone | timezone | ACTIVE | local-time/circadian derivation |
| provider_status | status.short/long | ACTIVE | pregame/result state |
| league_id | league.id | ACTIVE | coverage/model segmentation |
| season | league.season | ACTIVE | season identity |
| home_team_id | teams.home.id | ACTIVE | team identity |
| away_team_id | teams.away.id | ACTIVE | team identity |
| home_score | scores.home | RESULT_ONLY | training/settlement only |
| away_score | scores.away | RESULT_ONLY | training/settlement only |

## 3.3 Derived schedule variables — zero extra provider requests

From historical/current /games data:

- days rest;
- hours since previous game;
- back-to-back indicator;
- previous extra-inning context when provider history proves it;
- doubleheader indicator when fixture schedule proves it;
- home/away streak;
- road-trip/homestand length after venue registry exists;
- travel distance after venue registry exists;
- timezone shift after venue registry exists;
- local first-pitch hour;
- day/night bucket after solar/venue context exists;
- series context when deterministically derivable.

## 3.4 Excluded/noise

- logos → DISPLAY_ONLY;
- country flag → DISPLAY_ONLY;
- country name/code → identity/display, not direct predictive feature;
- free-text week → RAW_ONLY unless later proved meaningful;
- team/league names → DISPLAY_ONLY; use IDs for model identity.

Never use final scores from the current game as pregame features.

# 4. API-Sports /standings

## 4.1 Live-observed fields

Each team row exposed:

- position
- stage
- description
- form
- group.name
- games.played
- games.win.total
- games.win.percentage
- games.lose.total
- games.lose.percentage
- points.for
- points.against
- team identity
- league identity
- country identity

The same structural family was observed in MLB and NPB.

## 4.2 Approved use

| Variable | Status | Notes |
|---|---|---|
| games played | ACTIVE | sample-size/context |
| win percentage | ACTIVE | coarse team-strength baseline |
| loss percentage | DERIVED/REDUNDANT | retain; normally redundant with win% |
| runs for | ACTIVE | provider calls them points.for |
| runs against | ACTIVE | provider calls them points.against |
| run differential | DERIVED | runs_for - runs_against |
| runs scored/game | DERIVED | runs_for / games_played |
| runs allowed/game | DERIVED | runs_against / games_played |
| standings position | RESEARCH_ONLY | highly redundant; admission requires ablation |
| group/stage | DISPLAY_ONLY | competition context |
| form | RAW_ONLY | live samples were null; do not depend on it |
| description | REJECTED | free-text standings annotation |
| logos/flags | REJECTED_MODEL | UI only |

Do not call standings every 15 minutes.

# 5. API-Sports /teams/statistics

This endpoint was live-verified as an **object response**, not a list.

## 5.1 Exact live field tree — MLB and NPB

### Identity

- team.id
- team.name
- team.logo
- league.id
- league.name
- league.type
- league.logo
- league.season
- country.id
- country.name
- country.code
- country.flag

### Games played

- games.played.all
- games.played.home
- games.played.away

### Wins

- games.wins.all.total
- games.wins.all.percentage
- games.wins.home.total
- games.wins.home.percentage
- games.wins.away.total
- games.wins.away.percentage

### Losses

Provider spelling is loses.

- games.loses.all.total
- games.loses.all.percentage
- games.loses.home.total
- games.loses.home.percentage
- games.loses.away.total
- games.loses.away.percentage

### Runs scored

Provider calls this points.for.

- points.for.total.all
- points.for.total.home
- points.for.total.away
- points.for.average.all
- points.for.average.home
- points.for.average.away

### Runs allowed

Provider calls this points.against.

- points.against.total.all
- points.against.total.home
- points.against.total.away
- points.against.average.all
- points.against.average.home
- points.against.average.away

## 5.2 Model-ready canonical transformations

ACTIVE/DERIVED candidates:

- overall win%;
- home win%;
- away win%;
- overall run rate;
- home run rate;
- away run rate;
- overall runs allowed/game;
- home runs allowed/game;
- away runs allowed/game;
- overall run differential/game;
- home run differential/game;
- away run differential/game;
- home-vs-away performance delta;
- sample sizes for each split.

The totals and percentages are retained for provenance, but do not blindly include every algebraically redundant field in one model.

### Redundancy rule

Do not simultaneously feed games played, wins, losses, win%, and loss% without validation. These contain overlapping information and can create unnecessary collinearity/noise.

Prefer compact canonical features plus sample size.

# 6. Player-level data from API-Sports Baseball

Current production evidence:

- /players → provider explicitly returned endpoint does not exist.

Therefore:

- API-Sports Baseball player search: **REJECTED / endpoint absent**.
- existing repository players/statistics client method: **UNVERIFIED**.
- do not build a model dependency on it;
- do not spend routine production requests on it.

Starting pitchers, lineups, injuries, bullpen roles and Statcast-quality player data must come from a separately verified source unless a future live provider audit proves an API-Sports Baseball endpoint.

# 7. Odds bookmaker policy

Live /odds/bookmakers returned 30 bookmakers.

Canonical playable IDs:

| API id | Provider name | Policy |
|---:|---|---|
| **1** | **1xbet** | **PLAYABLE** |
| **2** | **Bet365** | **PLAYABLE** |
| 3–30 | other provider books | INTELLIGENCE_ONLY |

## Hard execution rule

A paper PICK can be registered only when its fresh verified entry quote is from:

- **1xBet**, or
- **Bet365**.

Other bookmakers may contribute:

- consensus probability;
- price dispersion;
- market movement;
- stale-price detection;
- cross-book disagreement;
- research/CLV context.

They can never become the registered executable quote.

# 8. Odds market catalog

Live /odds/bets returned 83 market definitions.

## 8.1 Production / planned production

| ID | Provider market | Policy |
|---:|---|---|
| **1** | **Home/Away** | ACTIVE V1 full-game moneyline |
| **5** | **Over/Under** | PLANNED V1 full-game totals |

Full-game totals require explicit line identity, for example 8.5, and separate Over/Under prices.

## 8.2 Research-only game-level candidates

These are not production picks yet. They remain available for later research if real Bet365/1xBet coverage exists and a proper model/settlement contract is built.

- 2 — Asian Handicap;
- 7 — Total - Home;
- 8 — Total - Away;
- 32 — Extra Innings;
- 33 — First Team To Score;
- 41 — Total Hits;
- 56 — Total Errors;
- 58 — Total Home Runs;
- 59 — Team with Highest Scoring Innings;
- 60 — Away Total Hits;
- 61 — Home Total Hits;
- 67 — Home Winning Margin;
- 68 — Away Winning Margin;
- 83 — Team With Highest Scoring.

No pick may be emitted from these markets merely because the provider catalog lists them.

## 8.3 Inning/F5/F7 markets — RAW_ONLY

Examples:

- Asian Handicap (1st 5 Innings)
- Money Line (1st 5 Innings)
- Over/Under (1st 5 Innings)
- 1x2 (1st Inning)
- Over/Under (1st Inning)
- Asian Handicap (1st Inning)
- 1x2 / ML / AH / O-U 1st 3 innings
- 1st 7 innings variants
- 4.5 innings variants

They require separate model semantics and are outside the current product.

## 8.4 Explicitly rejected three-way/generic ambiguity

- Match Winner id 14 is known from live raw payloads to contain Home/Draw/Away and is **not** the two-way MLB moneyline.
- Generic 1x2, Double Chance, HT/FT, Goals, Both Teams To Score, Shots and similarly named catalog entries are not canonical Baseball V1 markets.
- They remain raw evidence only unless a real Baseball payload proves an exact useful semantic contract.

## 8.5 Player props — permanently excluded

Provider catalog IDs observed include:

- 49 Player Total Bases
- 50 Player Singles
- 51 Player Runs
- 52 Player Doubles
- 53 Player Home Runs
- 54 Player Triples
- 55 Player Stolen Bases
- 73 Player Runs
- 74 Pitcher Earned Runs
- 75 Pitcher Outs
- 76 Player Hits
- 77 Player Runs Batted In
- 78 Pitcher Strikeouts
- 79 Pitcher Hits Allowed
- 80 Pitcher Walks Issued

These stay only in full raw payloads. They are excluded from compact canonical market processing and from product output.

# 9. Dynamic odds variables

From a real /odds game payload, retain raw:

- game identity;
- bookmaker id/name;
- bet/market id/name;
- outcome label;
- decimal price;
- handicap/line where present;
- provider capture timestamp.

Canonical decision variables:

- executable Bet365 home/away price;
- executable 1xBet home/away price;
- executable Bet365 total line/Over/Under prices once totals is activated;
- executable 1xBet total line/Over/Under prices once totals is activated;
- quote age;
- best playable price;
- de-vigged probability;
- multi-book market median/consensus;
- cross-book dispersion;
- Bet365-vs-consensus delta;
- 1xBet-vs-consensus delta;
- opening/current movement when historical observations exist;
- closing price for evaluation only;
- CLV after pick registration.

Closing prices are never pregame model features for a decision made before they existed.

# 10. MLB maximum research variable universe beyond current API fields

The project should seek maximum useful pregame evidence. Official MLB source contracts for probable starters, roster/transactions, venue metadata and replayable pregame feed state are now **source-verified**, but their canonical variables remain **EXTERNAL_PENDING** until durable point-in-time ingestion and archive provenance are implemented.

## 10.0 Official MLB source contract now verified

| Evidence family | Verified source | Current registry status | Admission note |
|---|---|---|---|
| probable starter identity | MLB schedule hydrate + game feed | EXTERNAL_PENDING | source verified; persist probable/confirmed state and timestamp before model use |
| batting order / lineup-capable state | MLB game feed boxscore | EXTERNAL_PENDING | historical pregame batting orders verified; expected vs confirmed state must remain separate |
| active roster | MLB team roster | EXTERNAL_PENDING | source verified; roster date and capture timestamp required |
| transactions | MLB transactions | EXTERNAL_PENDING | source verified; effective date and capture timestamp required |
| venue identity/location/time zone/field metadata | MLB game feed | EXTERNAL_PENDING | candidate source for canonical venue registry; static fields should be cached/versioned |
| historical pregame replay | MLB game feed `timecode` | EXTERNAL_PENDING | feasible, but actual `metaData.timeStamp` is the authoritative cutoff, not requested timecode |
| MLB feed weather | MLB game feed | RAW_ONLY / OPTIONAL | sampled early-pregame payload was empty; do not depend on it or coerce absence to zero |

No official MLB field becomes a model input merely because the endpoint is now verified. Durable raw archiving, canonicalization, null-reason semantics and chronological validation remain mandatory.

## 10.1 Starting pitcher

Desired:

- probable/confirmed starter;
- throwing hand;
- days rest;
- prior-start workload;
- rolling workload;
- K%, BB%, K-BB%;
- velocity and velocity trend;
- pitch mix;
- whiff/chase metrics;
- batted-ball quality allowed;
- platoon splits;
- expected starter length.

Preferred external classes:

- official MLB probable starter/lineup data;
- Baseball Savant/Statcast where structured/replayable.

## 10.2 Bullpen

Desired:

- relievers used previous 1/2/3 days;
- pitches/innings recent;
- consecutive-day use;
- closer/setup availability proxy;
- high-leverage reliever availability;
- bullpen quality;
- bullpen fatigue score.

## 10.3 Injuries and roster availability

Desired:

- injured-list status;
- official roster transactions;
- starter scratch;
- hitter availability;
- reliever availability;
- role-aware impact;
- replacement quality.

Do not use generic injury count.

## 10.4 Confirmed lineup

Desired:

- batting order 1–9;
- confirmed timestamp;
- handedness composition;
- missing regulars;
- catcher/DH identity;
- lineup strength vs RHP/LHP;
- change from expected lineup.

Expected and confirmed lineup states must never be conflated.

## 10.5 Statcast/offense/pitching

Desired candidate families:

- exit velocity;
- hard-hit%;
- barrel%;
- xBA/xSLG/xwOBA-type expected metrics where available;
- whiff%;
- chase%;
- pitch velocity;
- spin;
- pitch-type mix;
- batted-ball profile;
- platoon splits.

These require chronological validation and sensible sample shrinkage.

## 10.6 Park / venue / roof

Desired static registry:

- stadium ID;
- latitude/longitude;
- elevation;
- roof type;
- current roof state when available;
- park factor version;
- field orientation only if verified;
- relevant dimensions.

Static venue data must not be fetched every game.

## 10.7 Weather

Open-Meteo integration candidate variables:

- temperature;
- relative humidity;
- dew point;
- surface pressure;
- precipitation probability;
- precipitation amount;
- cloud cover;
- visibility if admitted;
- wind speed;
- wind direction;
- wind gusts;
- weather code;
- day/night state.

Derived candidates:

- mean expected game temperature;
- temperature change during game;
- outward/inward wind component once verified stadium orientation exists;
- air-density proxy;
- precipitation/delay risk proxy;
- day/night/twilight;
- park × weather interactions.

Outside weather is not applied to fixed domes or a verified closed retractable roof.

## 10.8 Schedule/travel/time of day

Derived from schedule + venue data without repeated provider calls:

- rest days/hours;
- travel distance;
- 24h/48h/72h travel load;
- timezone changes;
- eastbound/westbound travel;
- road-trip/homestand length;
- local first-pitch time;
- body-clock/circadian proxy;
- day/night;
- doubleheader;
- previous extra-inning workload.

Time-of-day variables are experimental until they add stable chronological signal.

# 11. Feature admission rules

A field enters the active model only when all are true:

1. exact meaning is known;
2. source is verified;
3. available before the decision cutoff;
4. timestamp/provenance is stored;
5. historical replay is possible;
6. no target leakage;
7. missingness is explicit;
8. out-of-sample chronological tests exist;
9. calibration is not degraded materially;
10. it provides stable incremental information.

Maximum data capture does **not** mean maximum model dimensionality.

# 12. API-burn policy

## Never every 15 minutes

These are static or slow-changing:

| Source | Refresh |
|---|---|
| /odds/bets | weekly or after documented provider schema change |
| /odds/bookmakers | weekly or after provider change |
| league metadata | infrequent/cache |
| venue coordinates/dimensions | static versioned registry |
| park-factor version | scheduled periodic refresh |
| standings | daily or materially slower than odds |
| team season statistics | once daily / after completed game window |

## Efficient historical acquisition

Prefer:

- one league/season history acquisition and local derivation;
- raw archive replay;
- local rolling-window calculations;
- persisted canonical snapshots.

Do not repeatedly request old games to recompute rest, form or H2H.

## Dynamic data priority

Provider request priority:

1. final playable quote for an active candidate;
2. registered-pick monitoring/closing;
3. settlement/result facts;
4. fresh odds for games inside the useful provider availability window;
5. broad discovery only with spare budget.

## Odds request efficiency

One game odds response can contain many bookmakers and markets.

Production burn findings on 2026-09-26:

- broad collection now selects only games whose adaptive cadence is due;
- successful provider odds responses are persisted as immutable `odds_poll_attempts`, including empty responses;
- adaptive cadence uses the latest **successful poll attempt**, not only the latest parsed quote row;
- a successful empty response is evidence that the provider was checked, but it is never fabricated into a quote;
- provider/API errors do not create successful poll-attempt evidence.

Therefore:

- do not make separate API-Sports requests for Bet365 and 1xBet if one game odds request already returns both;
- do not refresh a game just to rediscover static market/bookmaker catalogs;
- do not query games far outside empirically useful odds coverage windows;
- do not poll player props because they are not a product;
- do not re-poll a game merely because the previous successful response contained zero market rows.

# 13. Model compactness policy — remove meaningless/redundant variables

REJECTED as direct model features:

- team logos;
- league logos;
- country flags;
- arbitrary text descriptions;
- provider display names when stable IDs exist;
- duplicate win/loss percentages that are algebraically redundant;
- duplicate totals + averages when one can be derived from the other and sample size;
- player-prop prices;
- generic sportsbook catalog labels without proven Baseball semantics;
- postgame current-game score;
- closing odds captured after the decision;
- narrative sentiment;
- unsupported motivation variables.

Retain their raw evidence when the provider supplied it, but do not feed them blindly into the model.

# 14. Market-specific feature emphasis

## Moneyline

Highest-priority candidate families:

- starting pitcher;
- bullpen availability/quality;
- confirmed lineup/offense;
- team strength;
- home/away splits;
- park;
- relevant weather/roof;
- rest/travel;
- playable odds;
- market consensus/dispersion.

## Full-game Over/Under

Highest-priority candidate families:

- both starting pitchers;
- both bullpens;
- both lineups/offenses;
- park factor;
- roof;
- temperature;
- wind;
- humidity/dew point/pressure-derived air-density context;
- total-run environment;
- exact total line;
- playable Over/Under prices.

Moneyline and totals may share raw evidence but require separate calibrated probability targets.

# 15. Current hard boundaries

- Real-money execution: **OFF**
- Paper mode: **ON**
- Paper stake target: **300 RSD singles**
- Playable books: **1xBet + Bet365 only**
- Player props: **OFF permanently**
- Current production market: **full-game Moneyline**
- Next market: **full-game Over/Under**
- Scheduled collection: **ON** after operational acceptance.
- Canary execution: **OFF** after successful acceptance.
- Adaptive odds cadence: **ON**, with successful empty polls persisted so missing quotes do not force 15-minute rediscovery.
