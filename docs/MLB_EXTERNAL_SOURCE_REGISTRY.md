# MLB External Source Registry

**Status:** evidence-backed source plan  
**Scope:** MLB-only enrichment outside API-Sports Baseball  
**Rule:** no source becomes an ACTIVE model input until capture timestamps, point-in-time semantics, archival, replay, and missingness are implemented.

The project prefers official/free sources and derives repeated features locally. External enrichment must not consume the API-Sports request budget.

## 1. Source priority

1. Official MLB source
2. Baseball Savant / Statcast
3. Open-Meteo for weather
4. Derived local features from archived schedule/venue/history
5. Secondary sources only when an official source does not exist and the source contract is independently verified

No narrative article is a canonical model feed.

---

## 2. MLB Probable Pitchers

**Source class:** official MLB  
**Public surface:** MLB Probable Pitchers date pages  
**Status:** VERIFIED SOURCE, ingestion pending

Verified useful fields/content:

- game matchup;
- scheduled game time;
- venue;
- probable starter name;
- handedness;
- starter status including TBD;
- basic displayed season context such as W-L, ERA and strikeouts.

### Canonical variables

- home_probable_starter_id/name
- away_probable_starter_id/name
- home_probable_starter_hand
- away_probable_starter_hand
- starter_status: PROBABLE / TBD / CHANGED / CONFIRMED when independently confirmed
- source_observed_at
- source_url/ref

### Rules

- Preserve every starter-status transition.
- A probable starter is not a confirmed starter.
- A late scratch must invalidate/rebuild pitcher-dependent feature snapshots.
- Do not scrape narrative preview prose into the model.

### Refresh policy

Pregame only and event-driven/time-bucketed:

- low frequency >24h before first pitch;
- moderate refresh inside 24h;
- tighter only for active research candidates close to game time;
- stop after confirmed/locked state unless a change is observed.

---

## 3. MLB Starting Lineups

**Source class:** official MLB  
**Public surface:** MLB Starting Lineups date/team pages  
**Status:** VERIFIED SOURCE, ingestion pending

Verified content:

- batting order;
- player identity/name;
- batter handedness;
- defensive position;
- probable/starting pitchers shown with game context;
- lineup publication changes over time.

### Canonical variables

For each team:

- lineup_status: MISSING / EXPECTED / OFFICIAL
- lineup_observed_at
- batting_slot_1 ... batting_slot_9
- player identity
- batting hand
- defensive position
- catcher identity
- DH identity
- number of regulars absent
- lineup platoon composition

### Derived variables

- lineup quality vs RHP/LHP
- expected-vs-confirmed lineup delta
- top-order quality
- bottom-order weakness
- handedness balance
- catcher/offense tradeoff
- missing regular impact

### Rules

- Never treat an expected lineup as official.
- Store the publication timestamp/source evidence.
- A confirmed-lineup change after a model snapshot invalidates affected features.
- Do not poll every game every few minutes when no lineup publication window is near.

---

## 4. MLB Injury Report

**Source class:** official MLB  
**Public surface:** MLB Injury Report  
**Status:** VERIFIED SOURCE, ingestion pending

Useful evidence classes:

- injured-list placement;
- activation/return;
- body area / reported injury description;
- current availability context.

### Canonical variables

- player_id/name
- team
- roster_role
- availability_state
- IL type where known
- injury/body-area text retained as evidence
- effective date
- observed_at

### Model variables

Do not use raw injury count.

Use role-aware derived impact:

- starting pitcher unavailable
- projected starter scratched
- high-leverage reliever unavailable
- closer/setup availability
- everyday hitter unavailable
- catcher unavailable
- replacement-quality delta
- number of unavailable regulars weighted by projected role

---

## 5. MLB Transactions

**Source class:** official MLB  
**Public surface:** MLB Transactions date pages  
**Status:** VERIFIED SOURCE, ingestion pending

Useful transaction types include:

- placed on injured list;
- activated from injured list;
- rehab assignment;
- recalled;
- optioned;
- designated for assignment;
- released;
- roster activation/deactivation.

### Uses

Transactions are authoritative roster-state evidence and a backstop for injury pages.

Derived features:

- current active-roster eligibility
- recent activation
- rehab-return recency
- bullpen call-up/down churn
- replacement player identity
- recent roster disruption count, role-weighted

Jersey-number changes and administratively irrelevant transactions are retained only if present in raw evidence and excluded from modeling.

---

## 6. Baseball Savant / Statcast

**Source class:** official MLB Baseball Savant  
**Public surface:** Statcast Search + CSV documentation  
**Status:** VERIFIED SOURCE, ingestion design pending

The official Statcast search supports querying by player, team, game and season. CSV documentation exposes granular pitch and batted-ball variables.

### Pitching candidates

- pitch type
- release speed / velocity
- release position
- spin rate
- spin axis
- pitch movement
- extension
- whiffs
- chase/swing outcomes when derivable
- called strikes / swinging strikes
- batted-ball outcomes allowed
- xwOBA/xERA-type expected quality
- platoon splits
- pitch-mix share
- velocity trend
- pitch-mix change
- workload/pitch count from archived events

### Hitting candidates

- exit velocity
- launch angle
- hard-hit rate
- barrel rate
- xBA
- xSLG
- xwOBA
- bat speed
- fast-swing rate
- swing length
- attack angle
- platoon splits

### Fielding/catching candidates

Only admit if incremental value survives chronological tests:

- catcher pop time
- throwing/arm strength
- other verified fielding measures

### Important exclusions

Do not use current-game post-event values in a pregame snapshot.

Raw Statcast fields such as post-pitch scores, post-event win-expectancy changes, and target-leaking game-state outcomes are historical event evidence only; they are never contemporaneous pregame predictors for the same game.

### API-burn policy

Statcast is outside the API-Sports budget, but still must be efficient:

- ingest historical ranges in batches;
- persist raw snapshots;
- compute rolling features locally;
- do not re-download full seasons for every game;
- incremental append by date;
- cache player/team aggregates keyed by cutoff.

---

## 7. Weather — Open-Meteo

**Source class:** external free structured weather  
**Status:** foundation already implemented in the repository

Current candidate fields:

- temperature
- relative humidity
- dew point
- precipitation probability
- precipitation
- surface pressure
- cloud cover
- wind speed
- wind direction
- wind gusts
- weather code

Derived only after venue geometry is verified:

- wind out/in component
- crosswind
- air-density proxy
- temperature trend through expected game window
- precipitation/delay-risk proxy
- park × weather interaction

No outdoor weather effect is applied to a fixed dome or a verified closed retractable roof.

---

## 8. Venue / park registry

**Source priority:** official MLB venue identity + versioned local static registry  
**Status:** REQUIRED BEFORE weather is model-active

Canonical static fields:

- provider venue/team mapping
- stadium name
- latitude
- longitude
- elevation
- roof type: OPEN / FIXED_DOME / RETRACTABLE
- field orientation only when verified
- dimensions/version
- park-factor version and source

Static venue fields must be versioned and cached. They must never be fetched every 15-minute worker cycle.

Roof **state for a specific game** is dynamic evidence and must not be inferred solely from roof type.

---

## 9. Schedule / rest / travel / circadian variables

**Source:** archived API-Sports /games + venue registry  
**Provider cost after collection:** ZERO

Derive locally:

- rest days
- exact hours since previous game
- doubleheader status
- previous extra-inning burden when evidence supports it
- road-trip/homestand length
- travel distance
- 24h / 48h / 72h travel load
- timezone changes
- eastbound / westbound shift
- local first-pitch hour
- body-clock hour proxy
- day/night/twilight state

These variables are experimental until chronological ablation proves stable incremental information.

---

## 10. Bullpen availability

**Sources:** historical game/Statcast participation + roster/transaction evidence  
**Provider cost after ingestion:** derived locally

Preferred variables:

- relievers used yesterday
- relievers used on consecutive days
- pitches thrown last 1/2/3 days
- innings last 1/2/3 days
- high-leverage arms likely unavailable
- closer/setup availability
- bullpen quality baseline
- bullpen fatigue score
- recent bullpen workload concentration

Avoid a simplistic team-level "bullpen tired" boolean.

---

## 11. Source admission contract

Every external source must provide or support:

1. canonical entity mapping;
2. capture timestamp;
3. source reference;
4. raw immutable archive;
5. point-in-time cutoff;
6. explicit missingness;
7. replay/backtest path;
8. change detection where data can be revised;
9. rate/burn policy;
10. deterministic transformation into features.

Until all ten exist, the source remains research-only and cannot silently enter production model inputs.

---

## 12. Noise / reject list

Do not model:

- logos
- flags
- article sentiment
- unsupported motivation narratives
- jersey-number changes
- raw injury count without role/value
- duplicated algebraic stats
- player props
- closing data not available at decision time
- same-game final scores or post-event features
- weather for closed/fixed domes as though outdoors
- inferred confirmed lineups before official confirmation
- inferred confirmed starters from stale probable-pitcher pages

---

## 13. MLB feature priority

### Tier A — must-have before serious MLB model

- starting pitcher identity/hand/quality/workload
- bullpen quality + availability
- confirmed/expected lineup state
- offense quality and platoon context
- team baseline strength
- park/roof
- weather where relevant
- rest/travel
- Bet365/1xBet executable market evidence

### Tier B — high-value refinement

- Statcast expected metrics
- velocity/pitch-mix trends
- barrel/hard-hit quality
- lineup quality delta
- role-weighted injuries
- market consensus/dispersion from intelligence-only books
- park × weather interactions

### Tier C — admit only if ablation earns it

- circadian/time-zone interactions
- fielding/catching micro-metrics
- fine-grained bat tracking
- complex travel windows
- interaction-heavy features

Maximum source coverage does not imply maximum final feature count.
