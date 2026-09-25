-- QuantBet Baseball moneyline decision / verification / registration lifecycle
-- Migration: 004_moneyline_decision_chain

BEGIN;

CREATE TABLE IF NOT EXISTS model_predictions (
    prediction_id UUID PRIMARY KEY,
    game_id TEXT NOT NULL REFERENCES fixtures(game_id) ON DELETE RESTRICT,
    model_version TEXT NOT NULL,
    feature_snapshot_ref TEXT NOT NULL,
    source_data_cutoff_at TIMESTAMPTZ NOT NULL,
    predicted_at TIMESTAMPTZ NOT NULL,
    home_probability NUMERIC(12,10) NOT NULL,
    away_probability NUMERIC(12,10) NOT NULL,
    uncertainty_metric NUMERIC(12,10) NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT model_predictions_time_valid
        CHECK (source_data_cutoff_at <= predicted_at),
    CONSTRAINT model_predictions_home_probability_valid
        CHECK (home_probability > 0 AND home_probability < 1),
    CONSTRAINT model_predictions_away_probability_valid
        CHECK (away_probability > 0 AND away_probability < 1),
    CONSTRAINT model_predictions_two_way_valid
        CHECK (ABS((home_probability + away_probability) - 1.0) <= 0.000000001),
    CONSTRAINT model_predictions_uncertainty_valid
        CHECK (uncertainty_metric >= 0),
    CONSTRAINT model_predictions_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_model_predictions_game_time
    ON model_predictions (game_id, predicted_at DESC, prediction_id DESC);

CREATE TABLE IF NOT EXISTS value_evaluations (
    evaluation_id UUID PRIMARY KEY,
    prediction_id UUID NOT NULL
        REFERENCES model_predictions(prediction_id) ON DELETE RESTRICT,
    game_id TEXT NOT NULL REFERENCES fixtures(game_id) ON DELETE RESTRICT,
    bookmaker TEXT NOT NULL,
    home_observation_id UUID NOT NULL
        REFERENCES odds_observations(observation_id) ON DELETE RESTRICT,
    away_observation_id UUID NOT NULL
        REFERENCES odds_observations(observation_id) ON DELETE RESTRICT,
    selected_observation_id UUID NOT NULL
        REFERENCES odds_observations(observation_id) ON DELETE RESTRICT,
    selection TEXT NOT NULL,
    stage TEXT NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL,
    quote_observed_at TIMESTAMPTZ NOT NULL,
    quote_age_seconds NUMERIC(14,3) NOT NULL,
    selected_odds NUMERIC(10,5) NOT NULL,
    market_probability NUMERIC(12,10) NOT NULL,
    model_probability NUMERIC(12,10) NOT NULL,
    fair_decimal_odds NUMERIC(12,6) NOT NULL,
    edge NUMERIC(12,10) NOT NULL,
    expected_value_per_unit NUMERIC(12,10) NOT NULL,
    uncertainty_metric NUMERIC(12,10) NOT NULL,
    min_edge NUMERIC(12,10) NOT NULL,
    min_expected_value NUMERIC(12,10) NOT NULL,
    outcome TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT value_evaluations_selection_valid
        CHECK (selection IN ('home', 'away')),
    CONSTRAINT value_evaluations_stage_valid
        CHECK (stage IN ('PRELIMINARY', 'FINAL')),
    CONSTRAINT value_evaluations_outcome_valid
        CHECK (outcome IN ('CANDIDATE', 'PASS')),
    CONSTRAINT value_evaluations_quote_time_valid
        CHECK (quote_observed_at <= evaluated_at),
    CONSTRAINT value_evaluations_quote_age_valid
        CHECK (quote_age_seconds >= 0),
    CONSTRAINT value_evaluations_selected_odds_valid
        CHECK (selected_odds > 1.0),
    CONSTRAINT value_evaluations_market_probability_valid
        CHECK (market_probability > 0 AND market_probability < 1),
    CONSTRAINT value_evaluations_model_probability_valid
        CHECK (model_probability > 0 AND model_probability < 1),
    CONSTRAINT value_evaluations_fair_odds_valid
        CHECK (fair_decimal_odds > 1.0),
    CONSTRAINT value_evaluations_uncertainty_valid
        CHECK (uncertainty_metric >= 0),
    CONSTRAINT value_evaluations_min_edge_valid
        CHECK (min_edge >= 0),
    CONSTRAINT value_evaluations_selected_observation_valid CHECK (
        (selection = 'home' AND selected_observation_id = home_observation_id)
        OR
        (selection = 'away' AND selected_observation_id = away_observation_id)
    ),
    CONSTRAINT value_evaluations_distinct_pair
        CHECK (home_observation_id <> away_observation_id),
    CONSTRAINT value_evaluations_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object'),
    CONSTRAINT value_evaluations_identity_unique
        UNIQUE (
            prediction_id,
            bookmaker,
            home_observation_id,
            away_observation_id,
            selection,
            stage
        )
);

CREATE INDEX IF NOT EXISTS idx_value_evaluations_game_stage_time
    ON value_evaluations (game_id, stage, evaluated_at DESC, evaluation_id DESC);

CREATE INDEX IF NOT EXISTS idx_value_evaluations_candidate
    ON value_evaluations (outcome, evaluated_at DESC, evaluation_id DESC);

CREATE TABLE IF NOT EXISTS final_quote_verifications (
    verification_id UUID PRIMARY KEY,
    preliminary_evaluation_id UUID NOT NULL UNIQUE
        REFERENCES value_evaluations(evaluation_id) ON DELETE RESTRICT,
    game_id TEXT NOT NULL REFERENCES fixtures(game_id) ON DELETE RESTRICT,
    bookmaker TEXT NOT NULL,
    selection TEXT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    reason_codes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    returned_home_observation_id UUID
        REFERENCES odds_observations(observation_id) ON DELETE RESTRICT,
    returned_away_observation_id UUID
        REFERENCES odds_observations(observation_id) ON DELETE RESTRICT,
    final_evaluation_id UUID
        REFERENCES value_evaluations(evaluation_id) ON DELETE RESTRICT,
    decided_at TIMESTAMPTZ,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT final_quote_verifications_selection_valid
        CHECK (selection IN ('home', 'away')),
    CONSTRAINT final_quote_verifications_status_valid
        CHECK (status IN ('REQUESTED', 'READY', 'REJECTED')),
    CONSTRAINT final_quote_verifications_pair_shape CHECK (
        (returned_home_observation_id IS NULL AND returned_away_observation_id IS NULL)
        OR
        (returned_home_observation_id IS NOT NULL AND returned_away_observation_id IS NOT NULL)
    ),
    CONSTRAINT final_quote_verifications_state_shape CHECK (
        (
            status = 'REQUESTED'
            AND cardinality(reason_codes) = 0
            AND returned_home_observation_id IS NULL
            AND returned_away_observation_id IS NULL
            AND final_evaluation_id IS NULL
            AND decided_at IS NULL
        )
        OR
        (
            status = 'READY'
            AND cardinality(reason_codes) = 0
            AND returned_home_observation_id IS NOT NULL
            AND returned_away_observation_id IS NOT NULL
            AND final_evaluation_id IS NOT NULL
            AND decided_at IS NOT NULL
        )
        OR
        (
            status = 'REJECTED'
            AND cardinality(reason_codes) > 0
            AND decided_at IS NOT NULL
        )
    ),
    CONSTRAINT final_quote_verifications_time_valid
        CHECK (decided_at IS NULL OR decided_at >= requested_at),
    CONSTRAINT final_quote_verifications_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_final_quote_verifications_status
    ON final_quote_verifications (status, requested_at, verification_id);

CREATE TABLE IF NOT EXISTS registered_picks (
    pick_id UUID PRIMARY KEY,
    verification_id UUID NOT NULL UNIQUE
        REFERENCES final_quote_verifications(verification_id) ON DELETE RESTRICT,
    final_evaluation_id UUID NOT NULL UNIQUE
        REFERENCES value_evaluations(evaluation_id) ON DELETE RESTRICT,
    prediction_id UUID NOT NULL
        REFERENCES model_predictions(prediction_id) ON DELETE RESTRICT,
    game_id TEXT NOT NULL REFERENCES fixtures(game_id) ON DELETE RESTRICT,
    market_family TEXT NOT NULL,
    selection TEXT NOT NULL,
    bookmaker TEXT NOT NULL,
    entry_observation_id UUID NOT NULL
        REFERENCES odds_observations(observation_id) ON DELETE RESTRICT,
    entry_odds NUMERIC(10,5) NOT NULL,
    model_probability NUMERIC(12,10) NOT NULL,
    market_probability NUMERIC(12,10) NOT NULL,
    fair_decimal_odds NUMERIC(12,6) NOT NULL,
    edge NUMERIC(12,10) NOT NULL,
    expected_value_per_unit NUMERIC(12,10) NOT NULL,
    uncertainty_metric NUMERIC(12,10) NOT NULL,
    model_version TEXT NOT NULL,
    feature_snapshot_ref TEXT NOT NULL,
    source_data_cutoff_at TIMESTAMPTZ NOT NULL,
    kickoff_at TIMESTAMPTZ NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL,
    paper_mode BOOLEAN NOT NULL,
    state TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT registered_picks_market_valid
        CHECK (market_family = 'moneyline'),
    CONSTRAINT registered_picks_selection_valid
        CHECK (selection IN ('home', 'away')),
    CONSTRAINT registered_picks_entry_odds_valid
        CHECK (entry_odds > 1.0),
    CONSTRAINT registered_picks_model_probability_valid
        CHECK (model_probability > 0 AND model_probability < 1),
    CONSTRAINT registered_picks_market_probability_valid
        CHECK (market_probability > 0 AND market_probability < 1),
    CONSTRAINT registered_picks_fair_odds_valid
        CHECK (fair_decimal_odds > 1.0),
    CONSTRAINT registered_picks_uncertainty_valid
        CHECK (uncertainty_metric >= 0),
    CONSTRAINT registered_picks_paper_only
        CHECK (paper_mode = TRUE),
    CONSTRAINT registered_picks_state_valid
        CHECK (state = 'REGISTERED'),
    CONSTRAINT registered_picks_cutoff_valid
        CHECK (source_data_cutoff_at <= registered_at),
    CONSTRAINT registered_picks_before_kickoff
        CHECK (registered_at < kickoff_at),
    CONSTRAINT registered_picks_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object'),
    CONSTRAINT registered_picks_one_moneyline_per_game
        UNIQUE (game_id, market_family)
);

CREATE INDEX IF NOT EXISTS idx_registered_picks_registered
    ON registered_picks (registered_at, pick_id);

COMMIT;
