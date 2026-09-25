# QuantBet Baseball — Research Feature Input Contract

**Status:** V1 contract  
**Product mode:** PAPER ONLY  
**Primary market:** full-game moneyline  
**Paper stake:** 300 RSD per registered single  
**Player-prop betting markets:** excluded

## 1. Core rule

The evidence layer and the model feature layer are deliberately different.

1. **Raw evidence keeps the complete provider response.**
2. **Canonical evidence keeps stable game/market identities and point-in-time provenance.**
3. **Feature snapshots admit only variables proven to have been available before the decision cutoff.**
4. A raw field is never promoted into a model merely because the API returned it.

This preserves future research value without allowing post-game or in-game leakage into pregame decisions.

## 2. Provider evidence policy

For every Baseball provider call used by research or production, retain:

- endpoint and request parameters;
- retrieval timestamp;
- provider payload checksum;
- immutable raw object-storage reference;
- the complete response body;
- canonical game/team/bookmaker identities where resolvable.

The current API-Sports raw archive therefore remains the lossless source even when the V1 model does not yet understand every returned field.

## 3. Game-level feature families

The model may use player-level information only to improve a **game-level** probability. It must never emit player-prop picks.

### Fixture and schedule

Candidate inputs:

- league / season;
- home and away team;
- scheduled first pitch;
- venue when available;
- game status;
- doubleheader context;
- schedule changes;
- home/away context;
- rest days derived from prior schedule;
- travel/context features only when deterministically derived from known schedule/venue facts.

### Team state and performance

Use every provider field that can be mapped point-in-time and has plausible predictive value, including where exposed:

- season record / standings state;
- home/away performance;
- runs scored / allowed;
- offensive and defensive rates;
- recent form;
- opponent-adjusted or split fields when available;
- team statistics returned by the provider.

Do not silently invent unavailable statistics.

### Pitching and player information

Player data are allowed only as model inputs for game probability.

Examples when the provider can establish them before first pitch:

- probable / confirmed starting pitcher identity;
- pitcher handedness;
- pitcher season/recent performance;
- workload and rest;
- bullpen workload/availability derived from prior games;
- expected/confirmed lineup information;
- batter/pitcher or platoon splits.

If API-Sports Baseball does not reliably expose a field, the field remains unavailable until a separate documented source is added.

### Market state

Retain the complete raw odds response.

V1 canonical decision inputs are restricted to full-game moneyline:

- bookmaker;
- exact home/away price pair;
- observed/retrieved timestamp;
- de-vigged market probability;
- line movement / opening-current-closing state derived only from stored observations;
- quote age;
- market coverage and dispersion where enough bookmakers are present.

Run line, totals and other game-level markets may remain in raw evidence for later research but do not become V1 paper picks.

Player-prop markets are not target markets and must not enter the decision/pick lifecycle.

## 4. Weather contract

Weather is a point-in-time feature source, not a post-game lookup.

Preferred initial source: Open-Meteo, because it supports live forecasts and archived historical forecasts without requiring another project secret.

Each MLB venue must resolve to a versioned stadium record containing at minimum:

- canonical venue name;
- latitude / longitude;
- timezone;
- roof type: OPEN_AIR / FIXED_DOME / RETRACTABLE / UNKNOWN.

For an outdoor-relevant game, capture the forecast nearest scheduled first pitch:

- temperature at 2 m;
- apparent temperature;
- relative humidity;
- dew point;
- surface / sea-level pressure;
- precipitation probability;
- precipitation amount;
- weather code;
- cloud cover;
- wind speed at 10 m;
- wind direction at 10 m;
- wind gusts at 10 m.

Roof handling:

- FIXED_DOME: outdoor weather is retained as context but marked model-ineligible by default;
- RETRACTABLE: weather eligibility requires a known roof-state policy or explicit roof-state evidence;
- OPEN_AIR: weather is eligible if the forecast existed before the feature cutoff;
- UNKNOWN: retain the forecast but fail closed for weather-derived model features.

Historical backtests must use archived forecasts that were available at the historical decision time when possible. Actual realized post-game weather must not be substituted for a pregame forecast feature.

## 5. Feature snapshot provenance

Every production/research prediction must point to one immutable feature snapshot containing:

- game ID;
- generated_at;
- source_data_cutoff_at;
- schema version;
- source payload references/checksums;
- feature names and values;
- feature availability flags;
- missingness reasons;
- model eligibility status.

For every feature:

`source_observed_at <= source_data_cutoff_at <= predicted_at < first_pitch`

A violation makes the feature snapshot ineligible for a pick.

## 6. Missing data policy

Missing data must be explicit.

Allowed outcomes include:

- AVAILABLE;
- NOT_EXPOSED_BY_PROVIDER;
- NOT_AVAILABLE_YET;
- STALE;
- IDENTITY_UNRESOLVED;
- WEATHER_NOT_RELEVANT_DOME;
- ROOF_STATE_UNKNOWN;
- LEAKAGE_CUTOFF_FAILED.

No silent zero-fill is permitted unless the imputation method is a versioned model feature validated out of sample.

## 7. Research dataset rule

Research retains both:

- registered paper picks;
- evaluated PASS cases.

This is necessary to measure selection bias, threshold quality, calibration, abstention and missed opportunities.

## 8. Paper economics

Every registered V1 moneyline pick is a single with:

- `paper_mode=true`;
- `paper_stake_rsd=300`;
- no real-money execution.

Settlement derives:

- WIN: `(entry_odds - 1) * 300`;
- LOSS: `-300`;
- PUSH: `0`.

Research reporting must expose at least:

- settled picks;
- W/L/P;
- total paper stake;
- realized RSD P/L;
- yield;
- drawdown;
- realized CLV availability and averages;
- model version;
- feature schema version.

## 9. Promotion rule

No new provider field or weather feature changes production decisions automatically.

Promotion sequence:

`raw evidence → canonical mapping → leakage audit → feature snapshot → chronological validation → walk-forward / untouched holdout → explicit model version`

The project remains PAPER_MODE until a separate explicit launch decision.
