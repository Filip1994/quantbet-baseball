# Baseball Research Feature Registry v2

**Status:** canonical variable and source policy  
**Updated:** 2026-09-26  
**Primary product:** game-level Baseball research, PAPER mode  
**Playable books:** Bet365 and 1xBet only  
**Markets in product scope:** full-game Moneyline; full-game Over/Under after its closed loop is implemented  
**Player props:** permanently excluded  
**Paper stake target:** 300 RSD per registered single

## 1. Governing rule

The engine follows:

`capture wide -> archive raw -> verify semantics -> verify point-in-time availability -> promote useful features -> test chronologically -> model`

"Maximum variables" means maximum credible evidence coverage, not maximum columns in the model.

A provider field is never promoted solely because it exists.

Every variable belongs to one of these classes:

| Class | Meaning |
|---|---|
| MODEL | Eligible to become a game-level model feature after chronological validation |
| MARKET | Market evidence used for probability, edge, executable quote or CLV |
| CONTROL | Needed for identity, scheduling, lifecycle, freshness or provenance; not predictive by itself |
| OUTCOME | Used only after first pitch for result/settlement/evaluation |
| RAW_ONLY | Archived for future research but not currently modeled |
| EXTERNAL | Required from a verified non-API-Sports source |
| REJECTED | Deliberately excluded as noise, leakage, unsupported semantics or out-of-scope product data |

No missing value is silently converted to zero.

## 2. Live-verified API-Sports Baseball surface

The following statements are based on live provider responses captured by the guarded Baseball Railway service on 2026-09-26.

### 2.1 `/games`

A single live `/games?date=2026-09-26` response returned 35 games across MLB, NPB, Asian Games, CPBL, KBO, Elitserien, Bundesliga and Division 1.

MLB and sampled non-MLB rows exposed the same schema.

Verified fields:

| Provider field | Class | Use |
|---|---|---|
| id | CONTROL | canonical game identity |
| date | CONTROL / MODEL-derived | first pitch; derive rest/time-of-day with point-in-time schedule |
| time | CONTROL | display only when redundant with timestamp/date |
| timestamp | CONTROL | canonical temporal ordering |
| timezone | CONTROL | normalize local/UTC schedule |
| week | REJECTED from model | provider schedule label; retain raw only |
| status.long | CONTROL | lifecycle |
| status.short | CONTROL | lifecycle |
| country.id/name/code | CONTROL | league geography / identity |
| country.flag | REJECTED | presentation asset only |
| league.id | CONTROL | canonical competition identity |
| league.name | CONTROL / segmentation | league-level research grouping |
| league.type | CONTROL | identity |
| league.season | CONTROL | season key |
| league.logo | REJECTED | presentation asset only |
| teams.home.id | CONTROL | team identity |
| teams.home.name | CONTROL | display/identity |
| teams.home.logo | REJECTED | presentation asset only |
| teams.away.id | CONTROL | team identity |
| teams.away.name | CONTROL | display/identity |
| teams.away.logo | REJECTED | presentation asset only |
| scores.home | OUTCOME | result/settlement only |
| scores.away | OUTCOME | result/settlement only |

The live `/games` response did **not** contain:

- injuries;
- probable/confirmed starting pitchers;
- lineups;
- player statistics;
- stadium/venue;
- roof;
- weather;
- umpire.

Therefore those must not be fabricated from `/games`.

### 2.2 `/standings`

Live MLB standings returned one response group containing 60 team rows.  
Live NPB standings returned one response group containing 12 team rows.

Verified row fields:

| Provider field | Class | Candidate use |
|---|---|---|
| position | MODEL candidate | season strength/context; validate incremental signal |
| games.played | MODEL / denominator | normalize rate and run-differential features |
| games.win.total | MODEL candidate | season baseline |
| games.win.percentage | MODEL candidate | season baseline |
| games.lose.total | MODEL candidate | season baseline |
| games.lose.percentage | MODEL candidate | season baseline |
| points.for | MODEL candidate | runs scored baseline |
| points.against | MODEL candidate | runs allowed baseline |
| group.name | CONTROL / segmentation | division/group context |
| stage | CONTROL / segmentation | competition stage |
| description | RAW_ONLY | provider competition annotation; do not NLP-model by default |
| form | RAW_ONLY pending evidence | live samples were null; no assumption that it is populated |
| team.id/name | CONTROL | identity |
| team.logo | REJECTED | presentation only |
| country / league identity | CONTROL | provenance / segmentation |

Preferred derived candidates from standings:

- win percentage;
- loss percentage;
- run differential = points.for - points.against;
- runs scored per game;
- runs allowed per game;
- run differential per game.

Do not use raw position as a substitute for underlying team strength without validation.

### 2.3 `/teams/statistics`

Live requests proved the endpoint exists and requires at least:

- `team`;
- `league`;
- season context used by the project.

The provider returns an object response rather than the list contract assumed by the generic client.

The first bounded audit archived the raw MLB and NPB responses before the generic parser rejected the object shape.

**Policy:** do not spend duplicate provider requests merely to rediscover that payload. The S3 raw-archive inventory is the authoritative next source for the exact field tree.

Until the archive inventory is incorporated below, individual team-stat field names are **PENDING_VERIFICATION** and must not be invented.

### 2.4 Player endpoint status

A live request to `/players?search=ohtani` returned:

`This endpoint do not exist.`

Therefore:

- generic `/players` search is REJECTED as an API-Sports Baseball dependency;
- do not burn requests retrying it;
- `players/statistics` remains unverified until an exact supported contract is proven from official/live evidence;
- starting-pitcher, lineup, injury and granular MLB player evidence must currently be treated as EXTERNAL unless a verified Baseball endpoint proves otherwise.

### 2.5 `/odds/bets`

Live response:

- 83 provider market definitions.

This endpoint is a catalog, not a per-cycle data source.

It should be fetched rarely and cached/versioned.

Product market policy:

| Market family | Product status |
|---|---|
| exact full-game `Home/Away` | ACTIVE Moneyline |
| exact full-game `Moneyline` if provider supplies it | accepted canonical alias only after exact semantics verification |
| exact full-game `Over/Under` | PLANNED/ACTIVE data collection for Totals v1 |
| `Match Winner` with Home/Draw/Away | REJECTED from two-way Moneyline |
| first-5 / first-3 / first-7 / inning variants | REJECTED from current product |
| team totals | REJECTED from current product |
| run line / spread | RAW_ONLY; not current product |
| player strikeouts/hits/HR/RBI/total bases/runs/etc. | REJECTED permanently as product markets |

Market matching must use exact canonical names/IDs, not broad substring tokens such as `total` or `winner`.

### 2.6 `/odds/bookmakers`

Live response:

- 30 provider bookmaker definitions;
- canonical sample confirmed `1xbet` as bookmaker ID 1.

Execution boundary:

| Bookmaker | Status |
|---|---|
| Bet365 | PLAYABLE |
| 1xBet / 1xbet | PLAYABLE |
| every other provider bookmaker | INTELLIGENCE_ONLY |

Rules:

1. A registered paper pick must reference Bet365 or 1xBet.
2. Final quote verification must use the same playable bookmaker identity.
3. Closing quote / CLV for the execution record must use the same playable-book methodology.
4. If neither playable book offers a valid fresh quote, result is PASS / NO_PLAYABLE_QUOTE.
5. The engine must never silently substitute Pinnacle, WilliamHill, Betano, Marathon, BetVictor or another bookmaker.
6. Other bookmakers may contribute to market consensus/dispersion research only.

## 3. MLB maximum evidence universe

MLB gets the richest evidence set available because free structured MLB-specific sources can supplement API-Sports.

### 3.1 API-Sports evidence used for MLB

Verified now:

- schedule/game identity;
- team identity;
- league/season;
- first-pitch timestamp/timezone;
- game lifecycle status;
- standings;
- season W/L rates;
- season runs for/against;
- bookmaker catalog;
- market catalog;
- pregame odds;
- market movement from stored observations;
- Bet365/1xBet executable quotes when present.

Pending exact raw-schema inventory:

- `teams/statistics` fields.

Never assume unverified Baseball endpoints.

### 3.2 External MLB evidence

These are separate from API-Sports and require verified point-in-time ingestion.

High priority:

- probable starting pitcher;
- confirmed starting pitcher;
- starter handedness;
- starting lineup;
- lineup confirmation timestamp;
- injuries / IL / roster transactions;
- bullpen recent workload;
- pitcher workload/rest;
- Baseball Savant / Statcast batting and pitching quality;
- park factors;
- stadium coordinates/elevation;
- roof type/state where verifiable;
- weather forecast.

Candidate game-level derived features include:

#### Starting pitcher

- starter identity and confirmation state;
- throwing hand;
- days rest;
- prior-start workload;
- rolling workload;
- strikeout/walk quality;
- velocity trend;
- pitch mix;
- whiff/chase quality;
- hard contact/barrel quality allowed;
- platoon splits;
- expected starter length.

#### Bullpen

- bullpen innings last 1/2/3 days;
- reliever appearance counts;
- consecutive-day usage;
- high-leverage reliever availability;
- closer/setup availability;
- aggregate relief quality;
- fatigue-adjusted effective bullpen strength.

#### Batting / lineup

- confirmed batting order;
- expected lineup when not confirmed, explicitly marked expected;
- regular starters missing;
- lineup strength versus RHP/LHP;
- K%, BB%, power/contact profile;
- exit velocity / hard-hit / barrel signals where point-in-time safe;
- platoon composition;
- lineup strength delta from team baseline.

#### Defense / running

Use only if stable and demonstrably incremental:

- team/position defensive quality;
- Statcast fielding metrics;
- catcher/run-control evidence;
- baserunning value.

#### Rest / travel

Derive locally from the stored schedule and venue registry:

- days/hours rest;
- previous game finish;
- extra-inning fatigue;
- doubleheader status;
- consecutive games;
- road-trip/homestand length;
- venue-to-venue distance;
- timezone shift;
- east/west travel.

Do not spend provider requests for values that can be derived from already stored fixtures.

#### Park / roof

- venue identity;
- latitude/longitude;
- elevation;
- park factor;
- park-factor version;
- field orientation only with verified source;
- roof type;
- roof state if known pregame.

#### Weather

Open-Meteo forecast, captured before first pitch:

- temperature;
- humidity;
- dew point;
- surface pressure;
- precipitation probability;
- precipitation;
- cloud cover;
- visibility when useful;
- wind speed;
- wind direction;
- wind gusts;
- weather code;
- day/night state.

Derived only after validation:

- air-density proxy;
- wind outward/inward component when field orientation is verified;
- temperature trajectory during expected game window;
- rain-delay risk proxy;
- park x weather interaction.

Outdoor weather is not applied to a known closed/fixed roof.

## 4. Non-MLB league policy

Collection may remain broader than MLB, but **feature availability is league-specific**.

Verified cross-league parity:

- `/games` schema: same in sampled MLB/NPB/CPBL/KBO/etc.;
- `/standings`: same core structure confirmed for MLB and NPB.

Do not pretend MLB-only external features exist for other leagues.

For NPB/KBO/CPBL/other leagues:

1. use provider schedule/status;
2. use verified standings;
3. use verified team statistics only after exact endpoint coverage is demonstrated;
4. use available odds;
5. use Bet365/1xBet only for executable paper picks;
6. external weather/venue data can be added only with verified venue identity;
7. injuries/starters/lineups remain missing unless a credible structured point-in-time source is implemented.

Missing rich features should reduce confidence / eligibility rather than be imputed from MLB priors without evidence.

## 5. Market-specific feature relevance

### 5.1 Moneyline

Highest-priority evidence:

- confirmed/probable starter;
- starter quality and rest;
- bullpen quality and fatigue;
- confirmed lineup / lineup quality;
- team offensive baseline;
- team run prevention;
- season strength;
- park;
- meaningful weather/roof;
- rest/travel;
- playable Bet365/1xBet price;
- cross-book market consensus/dispersion.

### 5.2 Full-game Over/Under

Highest-priority evidence:

- both starting pitchers;
- both bullpens;
- both lineups/offenses;
- park factor;
- roof;
- temperature;
- wind;
- pressure/humidity/air-density candidates;
- bullpen fatigue;
- run-scoring baseline;
- exact total line;
- Bet365/1xBet Over and Under prices;
- market consensus at the **same exact line**.

Do not compare model probability for 8.5 against market 9.5.

### 5.3 Player props

REJECTED.

Player-level data may support the game model, but no player betting market is generated.

## 6. API-burn policy

The 7,500/day API limit is a ceiling, not a target.

### 6.1 Static / slow-changing catalogs

`odds/bets`, `odds/bookmakers`, league identity and similar catalogs:

- fetch only for explicit refresh/schema audit;
- cache/version locally;
- no per-cycle calls.

### 6.2 Schedule

- store fixture history durably;
- do not repeatedly refetch historical dates;
- discover relevant near-term games using bounded date pages;
- use game-by-ID refresh only for active lifecycle needs such as result settlement.

### 6.3 Standings

- one league snapshot can serve every game in that league;
- refresh on a coarse cadence, not every 15-minute worker cycle;
- archive each fresh response;
- derive team features locally.

### 6.4 Team statistics

- one team-season snapshot is reused across all candidate games until meaningful new game data can change it;
- do not fetch per model, per bookmaker or per odds refresh;
- prefer event-driven refresh after completed games or coarse daily caching.

### 6.5 Odds

Provider requests are prioritized:

1. active pick final/monitoring/closing needs;
2. settlement/result lifecycle;
3. games in a proven odds-availability window;
4. research discovery.

Do not scan every listed game every 15 minutes simply because budget exists.

Each odds response may contain multiple bookmakers. Do not make separate provider calls merely to fetch Bet365 and 1xBet if one response already returns both.

### 6.6 Weather / external data

Cache by venue + forecast generation + game window.

Do not call weather repeatedly when the source snapshot is still within the defined freshness policy.

## 7. Explicitly rejected/noise fields

Not model features:

- logos;
- flags;
- provider image URLs;
- textual schedule labels such as `week` unless later proven semantically valuable;
- raw IDs as numeric predictors;
- bookmaker ID as a causal baseball feature;
- league logo;
- team logo;
- final score before settlement;
- postgame stats in a pregame snapshot;
- closing line as an input to the earlier prediction;
- random news sentiment;
- generic "motivation";
- player-prop market values;
- arbitrary raw field dumps with no semantic contract.

Identity fields remain stored even when they are not predictive.

## 8. Point-in-time and leakage rules

Every model prediction references an immutable feature snapshot containing:

- game_id;
- snapshot_id;
- feature_version;
- generated_at;
- source_data_cutoff_at;
- kickoff_at;
- canonical feature values;
- source names;
- observed/captured timestamps;
- raw payload refs/checksums;
- missing reason codes.

Invariant:

`source_data_cutoff_at <= predicted_at < kickoff_at`

Historical training may only use information that was knowable at that historical cutoff.

## 9. Missingness

Examples:

- `STARTER_UNKNOWN`
- `LINEUP_NOT_CONFIRMED`
- `INJURY_SOURCE_UNAVAILABLE`
- `TEAM_STATS_UNAVAILABLE_FOR_LEAGUE`
- `WEATHER_NOT_APPLICABLE_ROOF_CLOSED`
- `ROOF_STATUS_UNKNOWN`
- `BET365_QUOTE_UNAVAILABLE`
- `1XBET_QUOTE_UNAVAILABLE`
- `NO_PLAYABLE_QUOTE`

Missing is never zero.

## 10. Feature admission

A candidate becomes an active model feature only when:

1. source and semantics are verified;
2. timestamp is point-in-time safe;
3. missingness is understood;
4. replay is possible;
5. transformation is versioned;
6. chronological out-of-sample testing exists;
7. calibration does not materially worsen;
8. the feature shows stable incremental information or useful uncertainty reduction.

Use ablation testing.

Intuition alone is insufficient.

## 11. Current implementation priorities

1. complete zero-request inventory of already archived provider payloads;
2. update this registry with the exact `teams/statistics` field tree and market/bookmaker catalogs;
3. enforce playable-book boundary Bet365/1xBet in the decision path;
4. preserve all other bookmaker observations for market intelligence only;
5. finish Moneyline live odds acceptance;
6. implement fixed 300 RSD paper stake migration safely;
7. integrate MLB external starter/lineup/injury/park/weather evidence;
8. build immutable feature snapshots;
9. validate a chronological model;
10. build full-game totals closed loop;
11. expose all evidence and system health in the read-only Baseball dashboard.
