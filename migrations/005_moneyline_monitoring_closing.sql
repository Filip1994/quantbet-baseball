-- QuantBet Baseball registered-pick monitoring and immutable closing facts
-- Migration: 005_moneyline_monitoring_closing

BEGIN;

CREATE TABLE IF NOT EXISTS pick_monitoring_states (
    pick_id UUID PRIMARY KEY
        REFERENCES registered_picks(pick_id) ON DELETE RESTRICT,
    state TEXT NOT NULL,
    lifecycle_policy_version TEXT NOT NULL,
    monitoring_interval_seconds INTEGER NOT NULL,
    current_max_age_seconds INTEGER NOT NULL,
    closing_max_age_seconds INTEGER NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    next_refresh_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL,
    version BIGINT NOT NULL,

    CONSTRAINT pick_monitoring_states_state_valid
        CHECK (state IN ('MONITORING', 'CLOSED_FOR_ODDS')),
    CONSTRAINT pick_monitoring_states_intervals_valid CHECK (
        monitoring_interval_seconds > 0
        AND current_max_age_seconds > 0
        AND closing_max_age_seconds > 0
    ),
    CONSTRAINT pick_monitoring_states_version_valid CHECK (version > 0),
    CONSTRAINT pick_monitoring_states_shape_valid CHECK (
        (state = 'MONITORING' AND next_refresh_at IS NOT NULL)
        OR
        (state = 'CLOSED_FOR_ODDS' AND next_refresh_at IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_pick_monitoring_due
    ON pick_monitoring_states (next_refresh_at, pick_id)
    WHERE state = 'MONITORING';

CREATE TABLE IF NOT EXISTS pick_monitoring_transitions (
    transition_id UUID PRIMARY KEY,
    pick_id UUID NOT NULL
        REFERENCES registered_picks(pick_id) ON DELETE RESTRICT,
    transition_type TEXT NOT NULL,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,

    CONSTRAINT pick_monitoring_transitions_type_valid
        CHECK (transition_type IN ('MONITORING_STARTED', 'ODDS_CLOSED')),
    CONSTRAINT pick_monitoring_transitions_from_valid
        CHECK (from_state IN ('REGISTERED', 'MONITORING')),
    CONSTRAINT pick_monitoring_transitions_to_valid
        CHECK (to_state IN ('MONITORING', 'CLOSED_FOR_ODDS')),
    CONSTRAINT pick_monitoring_transitions_shape_valid CHECK (
        (
            transition_type = 'MONITORING_STARTED'
            AND from_state = 'REGISTERED'
            AND to_state = 'MONITORING'
        )
        OR
        (
            transition_type = 'ODDS_CLOSED'
            AND from_state = 'MONITORING'
            AND to_state = 'CLOSED_FOR_ODDS'
        )
    ),
    CONSTRAINT pick_monitoring_transitions_once
        UNIQUE (pick_id, transition_type)
);

CREATE INDEX IF NOT EXISTS idx_pick_monitoring_transition_history
    ON pick_monitoring_transitions (pick_id, occurred_at, transition_id);

CREATE TABLE IF NOT EXISTS pick_closing_finalizations (
    finalization_id UUID PRIMARY KEY,
    pick_id UUID NOT NULL UNIQUE
        REFERENCES registered_picks(pick_id) ON DELETE RESTRICT,
    game_id TEXT NOT NULL REFERENCES fixtures(game_id) ON DELETE RESTRICT,
    fixture_observation_id UUID NOT NULL
        REFERENCES fixture_observations(fixture_observation_id) ON DELETE RESTRICT,
    cutoff_at TIMESTAMPTZ NOT NULL,
    bookmaker TEXT NOT NULL,
    selection TEXT NOT NULL,
    finalized_at TIMESTAMPTZ NOT NULL,
    outcome TEXT NOT NULL,
    candidate_home_observation_id UUID
        REFERENCES odds_observations(observation_id) ON DELETE RESTRICT,
    candidate_away_observation_id UUID
        REFERENCES odds_observations(observation_id) ON DELETE RESTRICT,
    closing_observation_id UUID
        REFERENCES odds_observations(observation_id) ON DELETE RESTRICT,
    lifecycle_policy_version TEXT NOT NULL,
    closing_max_age_seconds INTEGER NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pick_closing_finalizations_selection_valid
        CHECK (selection IN ('home', 'away')),
    CONSTRAINT pick_closing_finalizations_outcome_valid
        CHECK (outcome IN ('CAPTURED', 'STALE_QUOTE', 'NO_VALID_QUOTE')),
    CONSTRAINT pick_closing_finalizations_time_valid
        CHECK (finalized_at >= cutoff_at),
    CONSTRAINT pick_closing_finalizations_age_valid
        CHECK (closing_max_age_seconds > 0),
    CONSTRAINT pick_closing_finalizations_pair_shape CHECK (
        (
            candidate_home_observation_id IS NULL
            AND candidate_away_observation_id IS NULL
        )
        OR
        (
            candidate_home_observation_id IS NOT NULL
            AND candidate_away_observation_id IS NOT NULL
            AND candidate_home_observation_id <> candidate_away_observation_id
        )
    ),
    CONSTRAINT pick_closing_finalizations_outcome_shape CHECK (
        (
            outcome = 'CAPTURED'
            AND candidate_home_observation_id IS NOT NULL
            AND candidate_away_observation_id IS NOT NULL
            AND closing_observation_id IS NOT NULL
        )
        OR
        (
            outcome = 'STALE_QUOTE'
            AND candidate_home_observation_id IS NOT NULL
            AND candidate_away_observation_id IS NOT NULL
            AND closing_observation_id IS NULL
        )
        OR
        (
            outcome = 'NO_VALID_QUOTE'
            AND candidate_home_observation_id IS NULL
            AND candidate_away_observation_id IS NULL
            AND closing_observation_id IS NULL
        )
    ),
    CONSTRAINT pick_closing_finalizations_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_pick_closing_cutoff
    ON pick_closing_finalizations (cutoff_at, pick_id);

CREATE FUNCTION reject_baseball_pick_lifecycle_fact_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'baseball pick lifecycle facts are append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER baseball_pick_monitoring_transitions_append_only
    BEFORE UPDATE OR DELETE ON pick_monitoring_transitions
    FOR EACH ROW EXECUTE FUNCTION reject_baseball_pick_lifecycle_fact_mutation();

CREATE TRIGGER baseball_pick_closing_finalizations_immutable
    BEFORE UPDATE OR DELETE ON pick_closing_finalizations
    FOR EACH ROW EXECUTE FUNCTION reject_baseball_pick_lifecycle_fact_mutation();

COMMIT;
