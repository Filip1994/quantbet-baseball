-- QuantBet Baseball operational product, canary and acceptance facts
-- Migration: 007_operational_acceptance.sql

BEGIN;

CREATE TABLE IF NOT EXISTS collection_canary_runs (
    canary_id UUID PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL,
    max_api_requests INTEGER NOT NULL,
    max_odds_requests INTEGER NOT NULL,
    status TEXT NOT NULL,
    api_requests INTEGER NOT NULL,
    fixture_observations_inserted INTEGER NOT NULL,
    observations_inserted INTEGER NOT NULL,
    archive_objects_verified INTEGER NOT NULL,
    archive_verification_failures INTEGER NOT NULL,
    errors INTEGER NOT NULL,
    passed BOOLEAN NOT NULL,
    reason_codes TEXT[] NOT NULL DEFAULT '{}',
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT collection_canary_time_valid
        CHECK (finished_at >= started_at),
    CONSTRAINT collection_canary_limits_valid
        CHECK (max_api_requests > 0 AND max_odds_requests >= 0),
    CONSTRAINT collection_canary_counts_valid CHECK (
        api_requests >= 0
        AND fixture_observations_inserted >= 0
        AND observations_inserted >= 0
        AND archive_objects_verified >= 0
        AND archive_verification_failures >= 0
        AND errors >= 0
    ),
    CONSTRAINT collection_canary_status_valid
        CHECK (status IN ('collected', 'skipped_locked', 'failed')),
    CONSTRAINT collection_canary_schema_nonempty
        CHECK (length(trim(schema_version)) > 0),
    CONSTRAINT collection_canary_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_collection_canary_finished
    ON collection_canary_runs (finished_at DESC, canary_id DESC);

CREATE INDEX IF NOT EXISTS idx_collection_canary_passed
    ON collection_canary_runs (passed, finished_at DESC);

CREATE TABLE IF NOT EXISTS operational_acceptance_runs (
    acceptance_id UUID PRIMARY KEY,
    evaluated_at TIMESTAMPTZ NOT NULL,
    policy_version TEXT NOT NULL,
    status TEXT NOT NULL,
    criteria JSONB NOT NULL,
    budget JSONB NOT NULL,
    integrity_anomalies INTEGER NOT NULL,
    latest_canary_id UUID
        REFERENCES collection_canary_runs(canary_id) ON DELETE RESTRICT,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT operational_acceptance_status_valid
        CHECK (status IN ('READY', 'BLOCKED')),
    CONSTRAINT operational_acceptance_integrity_valid
        CHECK (integrity_anomalies >= 0),
    CONSTRAINT operational_acceptance_criteria_object
        CHECK (jsonb_typeof(criteria) = 'object'),
    CONSTRAINT operational_acceptance_budget_object
        CHECK (jsonb_typeof(budget) = 'object'),
    CONSTRAINT operational_acceptance_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_operational_acceptance_evaluated
    ON operational_acceptance_runs (evaluated_at DESC, acceptance_id DESC);

CREATE TRIGGER baseball_collection_canary_runs_append_only
    BEFORE UPDATE OR DELETE ON collection_canary_runs
    FOR EACH ROW EXECUTE FUNCTION reject_baseball_pick_lifecycle_fact_mutation();

CREATE TRIGGER baseball_operational_acceptance_runs_append_only
    BEFORE UPDATE OR DELETE ON operational_acceptance_runs
    FOR EACH ROW EXECUTE FUNCTION reject_baseball_pick_lifecycle_fact_mutation();

CREATE OR REPLACE VIEW baseball_moneyline_daily_bulletin AS
WITH latest_fixture AS (
    SELECT DISTINCT ON (game_id)
        game_id,
        league,
        home_team_name,
        away_team_name,
        kickoff_at,
        provider_status,
        observed_at AS fixture_observed_at
    FROM fixture_observations
    ORDER BY game_id, observed_at DESC, fixture_observation_id DESC
)
SELECT
    r.pick_id,
    r.game_id,
    f.league,
    f.away_team_name,
    f.home_team_name,
    r.selection,
    r.bookmaker,
    r.entry_odds,
    r.model_probability,
    r.market_probability AS entry_market_probability,
    r.edge,
    r.expected_value_per_unit,
    r.model_version,
    r.registered_at,
    r.kickoff_at,
    f.provider_status,
    f.fixture_observed_at,
    COALESCE(m.state, 'REGISTERED') AS lifecycle_state,
    c.outcome AS closing_outcome,
    c.finalized_at AS closing_finalized_at,
    s.outcome AS settlement_outcome,
    s.profit_per_unit,
    s.clv_status,
    s.closing_odds,
    s.clv_probability_delta,
    s.settled_at
FROM registered_picks r
LEFT JOIN latest_fixture f ON f.game_id = r.game_id
LEFT JOIN pick_monitoring_states m ON m.pick_id = r.pick_id
LEFT JOIN pick_closing_finalizations c ON c.pick_id = r.pick_id
LEFT JOIN pick_settlements s ON s.pick_id = r.pick_id;

CREATE OR REPLACE VIEW baseball_operational_integrity AS
SELECT
    (
        SELECT COUNT(*)
        FROM registered_picks r
        JOIN odds_observations o ON o.observation_id = r.entry_observation_id
        WHERE
            o.game_id <> r.game_id
            OR o.bookmaker <> r.bookmaker
            OR o.selection <> r.selection
            OR o.market_family <> r.market_family
    )::BIGINT AS entry_provenance_anomalies,
    (
        SELECT COUNT(*)
        FROM pick_closing_finalizations c
        JOIN registered_picks r ON r.pick_id = c.pick_id
        LEFT JOIN odds_observations o
            ON o.observation_id = c.closing_observation_id
        WHERE
            c.outcome = 'CAPTURED'
            AND (
                o.observation_id IS NULL
                OR o.game_id <> r.game_id
                OR o.bookmaker <> r.bookmaker
                OR o.selection <> r.selection
            )
    )::BIGINT AS closing_provenance_anomalies,
    (
        SELECT COUNT(*)
        FROM pick_settlements s
        JOIN registered_picks r ON r.pick_id = s.pick_id
        JOIN game_result_facts g ON g.result_id = s.result_id
        WHERE s.game_id <> r.game_id OR g.game_id <> r.game_id
    )::BIGINT AS settlement_provenance_anomalies;

COMMIT;
