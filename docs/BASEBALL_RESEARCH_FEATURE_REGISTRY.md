# Baseball Research Feature Registry v1

**Scope:** game-level Baseball research and paper moneyline picks only.  
**Player props:** permanently excluded.  
**Paper stake target:** 300 RSD per registered single.  
**Operating rule:** retain complete raw provider payloads, but expose only point-in-time-safe fields to a model.  
**Canonical live variable/market registry:** `docs/BASEBALL_VARIABLE_MARKET_REGISTRY.md`.

## 1. Core rule

"Use everything the API returns" means:

1. every fresh provider response is archived in full before canonicalization;
2. every model feature keeps source provenance and a cutoff timestamp;
3. fields that are post-game, in-game, stale, ambiguous, or not available at the decision time are retained as raw evidence but are not model inputs;
4. feature promotion is versioned and testable;
5. absence is explicit: missing, unavailable, not applicable, or provider-unsupported are distinct states.

This avoids losing potentially useful information without introducing look-ahead leakage.

## 2. Current provider surface

Live production evidence now verifies these useful API-Sports Baseball surfaces:

- games/schedule/results;
- standings;
- team statistics;
- pregame odds;
- odds bet-type catalog;
- odds bookmaker catalog.

The current repository still contains a legacy `players/statistics` client method, but it is **not an approved source**. A bounded live `/players` request on 2026-09-26 returned `endpoint does not exist`. Player-level API data therefore remains UNVERIFIED and must not be used until an exact live contract is proved.

The exact observed field trees, market classifications, bookmaker policy and API-refresh policy live in `docs/BASEBALL_VARIABLE_MARKET_REGISTRY.md`.

Official MLB Stats API source contracts are also now live-verified for probable starters, active roster, transactions, venue metadata and lineup-capable game-feed state. Historical `timecode` replay returned a genuine pregame snapshot with both probable starters and populated 9-player batting orders. These remain ingestion-pending until raw archival and canonical point-in-time storage are implemented.

Historical replay safety rule: persist and enforce the response `metaData.timeStamp`. A requested historical timecode can resolve to a slightly later provider snapshot, so requested time alone is not sufficient to prove absence of look-ahead leakage.

## 3. Feature families

### 3.1 Fixture and schedule context

Candidate fields/derivations:

- game ID;
- league/season;
- scheduled first pitch;
- home/away identity;
- provider game status;
- home/away schedule density;
- previous-game finish time;
- days/rest hours since previous game;
- travel proxy where venue coordinates are known;
- doubleheader indicator;
- series game number when derivable without future data.

Source:
- API-Sports Baseball `games` history and current schedule.

Point-in-time rule:
- only observations captured before the model cutoff.

### 3.2 Team strength and current state

Retain the full raw `standings` and `teams/statistics` responses.

Candidate modeled features are promoted only after their exact live schema is observed. Possible families include:

- win/loss record;
- home/away performance;
- runs scored/allowed;
- recent form;
- offensive rate statistics;
- defensive/pitching rate statistics;
- run differential;
- opponent-adjusted or rolling versions where enough history exists.

Do not hard-code provider field names until live payload inventory proves them.

### 3.3 Pitching

Starting pitching is a high-priority game-level input, not a player-prop product.

Candidate features when pregame identity/data are available:

- probable/confirmed starter identity;
- throwing hand;
- season and rolling run prevention;
- strikeout/walk indicators;
- workload and days rest;
- recent pitch/inning workload;
- home/away and handedness splits;
- opponent matchup aggregates.

Bullpen candidates:

- team bullpen usage over prior 1/2/3 days;
- recent innings/pitches where available;
- availability proxy;
- relief performance and handedness mix.

All pitcher/player data must be aggregated into game-level win-probability inputs.

### 3.4 Batting and lineup context

If the provider exposes reliable pregame lineup/player participation data, preserve it and derive team-level features such as:

- expected/confirmed batting order;
- missing regular starters;
- batter handedness mix;
- platoon splits versus opposing starter hand;
- rolling offense quality;
- lineup-strength delta versus team baseline.

No player betting markets are generated.

### 3.5 Market state

Executable paper-pick bookmakers are **1xBet (provider id 1)** and **Bet365 (provider id 2)** only. Other provider books may be retained for consensus/intelligence but cannot become the registered entry quote.

From immutable odds observations:

- bookmaker;
- playable/non-playable classification;
- home/away prices;
- de-vigged market probability;
- opening/current/final verified quote;
- quote age;
- cross-book dispersion;
- line movement;
- model-vs-market edge;
- CLV after closing.

Market prices are evidence and calibration inputs; they must not overwrite independently produced model probabilities.

### 3.6 Park, venue and roof

Required canonical venue context:

- stadium/venue identity;
- latitude/longitude;
- roof type;
- roof state when known;
- elevation;
- park-factor version.

Weather is not applied when the roof is known closed or the venue is a fixed indoor dome.

A static/reviewed venue registry is preferred over free-text geocoding at decision time.

### 3.7 Weather

Live source:
- Open-Meteo Forecast API.

Canonical pregame snapshot fields:

- temperature at first pitch;
- relative humidity;
- dew point;
- precipitation probability;
- precipitation amount;
- surface pressure;
- cloud cover;
- wind speed;
- wind direction;
- wind gusts;
- weather code.

The snapshot is taken at stadium coordinates and archived in full. The canonical row points to the archived payload checksum/ref.

For historical model work, do not use observed final weather as if it had been known pregame. Historical forecast/single-run data must be aligned to the decision cutoff.

### 3.8 Derived interaction features

Only after raw feature quality is verified:

- wind component toward/away from center field;
- temperature/air-density run-environment proxy;
- starter hand × opponent lineup handedness;
- bullpen fatigue × expected starter length;
- park × weather interaction;
- rest/travel × bullpen state;
- market disagreement × model uncertainty.

These are derived features; the raw components must remain available for replay.

## 4. Feature snapshot provenance contract

Every model prediction must reference one immutable feature snapshot containing at least:

- `game_id`;
- `snapshot_id`;
- `feature_version`;
- `generated_at`;
- `source_data_cutoff_at`;
- canonical feature values;
- per-source observation/capture timestamps;
- raw source refs/checksums;
- null/missing reason codes;
- venue/roof context;
- weather snapshot ref when applicable.

Invariant:

`source_data_cutoff_at <= predicted_at < kickoff_at`.

No model may consume a source captured after `source_data_cutoff_at`.

## 5. Raw-versus-model policy

### Always retain raw

- complete API-Sports envelopes for every called endpoint;
- complete Open-Meteo response used by the decision;
- provider fields not yet promoted to features;
- provider schema additions.

### Model eligibility requires

- pregame availability;
- stable identity/meaning;
- replayable provenance;
- acceptable missingness;
- no result leakage;
- documented transformation;
- chronological validation.

## 6. Activation sequence

Completed production gates:

1. full-game moneyline canonicalization validated against live provider schema;
2. bounded market-acceptance canary passed;
3. scheduled raw/canonical collection enabled with `PAPER_MODE=true`;
4. standings/team/game provider schemas inventoried;
5. Bet365/1xBet executable-book enforcement deployed;
6. fixed 300 RSD paper stake persisted;
7. adaptive odds polling hardened so only due games are selected and successful empty polls are durable evidence.

Current build sequence:

1. ingest verified official MLB probable-starter / roster / transaction evidence point-in-time;
2. create canonical venue/roof registry;
3. ingest expected/confirmed lineup states without conflation;
4. integrate weather snapshots;
5. assemble immutable feature snapshots using actual source timestamps;
6. train/evaluate chronological Moneyline V1;
7. produce genuine PICK/PASS decisions only after calibration acceptance;
8. close the first real 300 RSD paper lifecycle through settlement and CLV;
9. activate full-game totals only after Moneyline closes end to end.

## 7. Explicit non-goals

- no player-prop selection;
- no real-money execution;
- no automated bankroll staking;
- no live betting;
- no using postgame data in pregame features;
- no treating every raw provider field as automatically useful.
