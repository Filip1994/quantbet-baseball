-- QuantBet Baseball PostgreSQL foundation
-- Migration: 001_create_evidence_tables
-- Scope: canonical immutable evidence only. No ingestion, settlement, or retention jobs.

BEGIN;

CREATE TABLE IF NOT EXISTS odds_observations (
    observation_id UUID PRIMARY KEY,
    game_id TEXT NOT NULL,
    market_family TEXT NOT NULL,
    line NUMERIC(6,2) NOT NULL,
    selection TEXT NOT NULL,
    bookmaker TEXT NOT NULL,
    decimal_odds NUMERIC(10,5) NOT NULL,
    raw_price TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    source_payload_ref TEXT NOT NULL,
    source_payload_checksum CHAR(64) NOT NULL,
    schema_version TEXT NOT NULL,
    market_status TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT odds_observations_decimal_odds_valid CHECK (decimal_odds > 1.0),
    CONSTRAINT odds_observations_checksum_valid CHECK (source_payload_checksum ~ '^[0-9a-fA-F]{64}$'),
    CONSTRAINT odds_observations_timestamps_valid CHECK (retrieved_at >= observed_at),
    CONSTRAINT odds_observations_market_family_valid CHECK (market_family IN ('moneyline', 'full_game_total')),
    CONSTRAINT odds_observations_market_status_valid CHECK (market_status IN ('open', 'suspended', 'closed', 'unknown')),
    CONSTRAINT odds_observations_canonical_object CHECK (jsonb_typeof(canonical_record) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_odds_observations_game_market_time
    ON odds_observations (game_id, market_family, line, observed_at, bookmaker, selection);

CREATE INDEX IF NOT EXISTS idx_odds_observations_retrieved_at
    ON odds_observations (retrieved_at);

CREATE TABLE IF NOT EXISTS pick_events (
    pick_id UUID PRIMARY KEY,
    game_id TEXT NOT NULL,
    market_family TEXT NOT NULL,
    line NUMERIC(6,2) NOT NULL,
    selection TEXT NOT NULL,
    decision TEXT NOT NULL,
    decision_reason TEXT NOT NULL,
    decision_at TIMESTAMPTZ NOT NULL,
    model_version TEXT NOT NULL,
    feature_snapshot_ref TEXT NOT NULL,
    market_snapshot_ref TEXT NOT NULL,
    decision_decimal_odds NUMERIC(10,5),
    model_probability NUMERIC(12,10),
    fair_decimal_odds NUMERIC(12,6),
    market_implied_probability NUMERIC(12,10),
    edge NUMERIC(12,10),
    expected_value_per_unit NUMERIC(12,10),
    uncertainty_metric NUMERIC(12,10),
    source_data_cutoff_at TIMESTAMPTZ NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pick_events_decision_valid CHECK (decision IN ('BET', 'PASS')),
    CONSTRAINT pick_events_market_family_valid CHECK (market_family IN ('moneyline', 'full_game_total')),
    CONSTRAINT pick_events_canonical_object CHECK (jsonb_typeof(canonical_record) = 'object'),
    CONSTRAINT pick_events_probability_valid CHECK (
        model_probability IS NULL OR (model_probability >= 0 AND model_probability <= 1)
    ),
    CONSTRAINT pick_events_market_probability_valid CHECK (
        market_implied_probability IS NULL OR (market_implied_probability >= 0 AND market_implied_probability <= 1)
    ),
    CONSTRAINT pick_events_uncertainty_valid CHECK (
        uncertainty_metric IS NULL OR uncertainty_metric >= 0
    ),
    CONSTRAINT pick_events_cutoff_valid CHECK (source_data_cutoff_at <= decision_at),
    CONSTRAINT pick_events_pass_metrics_valid CHECK (
        decision <> 'PASS' OR (
            decision_decimal_odds IS NULL AND model_probability IS NULL AND fair_decimal_odds IS NULL
            AND market_implied_probability IS NULL AND edge IS NULL AND expected_value_per_unit IS NULL
            AND uncertainty_metric IS NULL
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_pick_events_game_decision_time
    ON pick_events (game_id, market_family, line, decision_at);

CREATE INDEX IF NOT EXISTS idx_pick_events_decision
    ON pick_events (decision, decision_at);

COMMIT;
