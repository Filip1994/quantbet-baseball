-- QuantBet Baseball operational canary, activation gate and performance diagnostics
-- Migration: 007_operational_acceptance

BEGIN;

ALTER TABLE collection_cycles
    ADD COLUMN IF NOT EXISTS execution_mode TEXT NOT NULL DEFAULT 'SCHEDULED';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'collection_cycles_execution_mode_valid'
    ) THEN
        ALTER TABLE collection_cycles
            ADD CONSTRAINT collection_cycles_execution_mode_valid
            CHECK (execution_mode IN ('SCHEDULED', 'CANARY'));
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_collection_cycles_mode_finished
    ON collection_cycles (execution_mode, finished_at DESC, cycle_id);

CREATE TABLE IF NOT EXISTS operational_canary_runs (
    canary_id UUID PRIMARY KEY,
    cycle_id UUID UNIQUE
        REFERENCES collection_cycles(cycle_id) ON DELETE RESTRICT,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    max_api_requests INTEGER NOT NULL,
    api_requests INTEGER NOT NULL,
    fixture_observations_inserted INTEGER NOT NULL,
    observations_inserted INTEGER NOT NULL,
    errors INTEGER NOT NULL,
    archive_verified BOOLEAN NOT NULL,
    db_write_verified BOOLEAN NOT NULL,
    reason_codes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT operational_canary_runs_status_valid
        CHECK (status IN ('PASSED', 'FAILED', 'SKIPPED_LOCKED')),
    CONSTRAINT operational_canary_runs_time_valid
        CHECK (finished_at >= started_at),
    CONSTRAINT operational_canary_runs_counts_valid CHECK (
        max_api_requests > 0
        AND api_requests >= 0
        AND api_requests <= max_api_requests
        AND fixture_observations_inserted >= 0
        AND observations_inserted >= 0
        AND errors >= 0
    ),
    CONSTRAINT operational_canary_runs_shape_valid CHECK (
        (
            status = 'PASSED'
            AND cycle_id IS NOT NULL
            AND errors = 0
            AND archive_verified = TRUE
            AND db_write_verified = TRUE
            AND cardinality(reason_codes) = 0
        )
        OR
        (
            status = 'FAILED'
            AND cardinality(reason_codes) > 0
        )
        OR
        (
            status = 'SKIPPED_LOCKED'
            AND cycle_id IS NOT NULL
            AND cardinality(reason_codes) > 0
        )
    ),
    CONSTRAINT operational_canary_runs_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_operational_canary_runs_finished
    ON operational_canary_runs (finished_at DESC, canary_id);

CREATE TABLE IF NOT EXISTS activation_gate_assessments (
    assessment_id UUID PRIMARY KEY,
    target TEXT NOT NULL,
    assessed_at TIMESTAMPTZ NOT NULL,
    verdict TEXT NOT NULL,
    reason_codes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    daily_request_budget INTEGER NOT NULL,
    cycle_request_cap INTEGER NOT NULL,
    cron_interval_minutes INTEGER NOT NULL,
    cycles_per_day INTEGER NOT NULL,
    worst_case_daily_requests INTEGER NOT NULL,
    request_headroom INTEGER NOT NULL,
    paper_mode BOOLEAN NOT NULL,
    collection_enabled BOOLEAN NOT NULL,
    api_key_configured BOOLEAN NOT NULL,
    raw_archive_configured BOOLEAN NOT NULL,
    migrations_current BOOLEAN NOT NULL,
    runtime_fresh BOOLEAN NOT NULL,
    canary_passed BOOLEAN NOT NULL,
    latest_canary_id UUID
        REFERENCES operational_canary_runs(canary_id) ON DELETE RESTRICT,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT activation_gate_target_valid
        CHECK (target IN ('CANARY', 'SCHEDULED_COLLECTION')),
    CONSTRAINT activation_gate_verdict_valid
        CHECK (verdict IN ('READY', 'BLOCKED')),
    CONSTRAINT activation_gate_budget_valid CHECK (
        daily_request_budget > 0
        AND cycle_request_cap > 0
        AND cron_interval_minutes > 0
        AND cron_interval_minutes <= 1440
        AND cycles_per_day > 0
        AND worst_case_daily_requests >= 0
    ),
    CONSTRAINT activation_gate_reason_shape CHECK (
        (verdict = 'READY' AND cardinality(reason_codes) = 0)
        OR
        (verdict = 'BLOCKED' AND cardinality(reason_codes) > 0)
    ),
    CONSTRAINT activation_gate_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_activation_gate_target_time
    ON activation_gate_assessments (target, assessed_at DESC, assessment_id);

CREATE TRIGGER baseball_operational_canary_runs_append_only
    BEFORE UPDATE OR DELETE ON operational_canary_runs
    FOR EACH ROW EXECUTE FUNCTION reject_baseball_pick_lifecycle_fact_mutation();

CREATE TRIGGER baseball_activation_gate_assessments_append_only
    BEFORE UPDATE OR DELETE ON activation_gate_assessments
    FOR EACH ROW EXECUTE FUNCTION reject_baseball_pick_lifecycle_fact_mutation();

CREATE OR REPLACE VIEW baseball_moneyline_evaluation_rows AS
SELECT
    s.pick_id,
    s.game_id,
    r.model_version,
    r.bookmaker,
    r.selection,
    r.model_probability,
    r.entry_odds,
    s.outcome,
    s.profit_per_unit,
    CASE
        WHEN s.outcome = 'WIN' THEN 1.0::NUMERIC
        WHEN s.outcome = 'LOSS' THEN 0.0::NUMERIC
        ELSE NULL::NUMERIC
    END AS actual_selected_win,
    s.clv_status,
    s.closing_market_probability,
    s.clv_probability_delta,
    s.clv_price_ratio,
    s.settled_at
FROM pick_settlements s
JOIN registered_picks r ON r.pick_id = s.pick_id;

CREATE OR REPLACE VIEW baseball_moneyline_performance AS
SELECT
    COUNT(*)::BIGINT AS settled_picks,
    COUNT(*) FILTER (WHERE outcome = 'WIN')::BIGINT AS wins,
    COUNT(*) FILTER (WHERE outcome = 'LOSS')::BIGINT AS losses,
    COUNT(*) FILTER (WHERE outcome = 'PUSH')::BIGINT AS pushes,
    COUNT(actual_selected_win)::BIGINT AS graded_probability_picks,
    COALESCE(SUM(profit_per_unit), 0)::NUMERIC(18,8) AS realized_profit_per_unit,
    CASE
        WHEN COUNT(*) = 0 THEN NULL
        ELSE (SUM(profit_per_unit) / COUNT(*))::NUMERIC(14,10)
    END AS roi_per_unit_staked,
    AVG(
        POWER(model_probability - actual_selected_win, 2)
    ) FILTER (
        WHERE actual_selected_win IS NOT NULL
    )::NUMERIC(14,10) AS brier_score,
    AVG(
        CASE
            WHEN actual_selected_win = 1
                THEN -LN(model_probability)
            WHEN actual_selected_win = 0
                THEN -LN(1 - model_probability)
            ELSE NULL
        END
    )::NUMERIC(14,10) AS log_loss,
    COUNT(*) FILTER (WHERE clv_status = 'AVAILABLE')::BIGINT AS clv_available,
    COUNT(*) FILTER (WHERE clv_status <> 'AVAILABLE')::BIGINT AS clv_unavailable,
    CASE
        WHEN COUNT(*) = 0 THEN NULL
        ELSE (
            COUNT(*) FILTER (WHERE clv_status = 'AVAILABLE')::NUMERIC
            / COUNT(*)::NUMERIC
        )::NUMERIC(12,10)
    END AS clv_coverage,
    AVG(clv_probability_delta) FILTER (
        WHERE clv_status = 'AVAILABLE'
    )::NUMERIC(14,10) AS average_clv_probability_delta,
    AVG(clv_price_ratio) FILTER (
        WHERE clv_status = 'AVAILABLE'
    )::NUMERIC(14,10) AS average_clv_price_ratio,
    CASE
        WHEN COUNT(*) FILTER (WHERE clv_status = 'AVAILABLE') = 0 THEN NULL
        ELSE (
            COUNT(*) FILTER (
                WHERE clv_status = 'AVAILABLE'
                AND clv_probability_delta > 0
            )::NUMERIC
            / COUNT(*) FILTER (WHERE clv_status = 'AVAILABLE')::NUMERIC
        )::NUMERIC(12,10)
    END AS positive_clv_rate
FROM baseball_moneyline_evaluation_rows;

CREATE OR REPLACE VIEW baseball_moneyline_performance_breakdown AS
SELECT
    'MODEL_VERSION'::TEXT AS dimension,
    model_version AS dimension_value,
    COUNT(*)::BIGINT AS settled_picks,
    COALESCE(SUM(profit_per_unit), 0)::NUMERIC(18,8) AS realized_profit_per_unit,
    CASE
        WHEN COUNT(*) = 0 THEN NULL
        ELSE (SUM(profit_per_unit) / COUNT(*))::NUMERIC(14,10)
    END AS roi_per_unit_staked,
    AVG(
        POWER(model_probability - actual_selected_win, 2)
    ) FILTER (
        WHERE actual_selected_win IS NOT NULL
    )::NUMERIC(14,10) AS brier_score,
    AVG(
        CASE
            WHEN actual_selected_win = 1
                THEN -LN(model_probability)
            WHEN actual_selected_win = 0
                THEN -LN(1 - model_probability)
            ELSE NULL
        END
    )::NUMERIC(14,10) AS log_loss,
    CASE
        WHEN COUNT(*) FILTER (WHERE clv_status = 'AVAILABLE') = 0 THEN NULL
        ELSE AVG(clv_probability_delta) FILTER (
            WHERE clv_status = 'AVAILABLE'
        )::NUMERIC(14,10)
    END AS average_clv_probability_delta
FROM baseball_moneyline_evaluation_rows
GROUP BY model_version

UNION ALL

SELECT
    'BOOKMAKER'::TEXT AS dimension,
    bookmaker AS dimension_value,
    COUNT(*)::BIGINT AS settled_picks,
    COALESCE(SUM(profit_per_unit), 0)::NUMERIC(18,8) AS realized_profit_per_unit,
    CASE
        WHEN COUNT(*) = 0 THEN NULL
        ELSE (SUM(profit_per_unit) / COUNT(*))::NUMERIC(14,10)
    END AS roi_per_unit_staked,
    AVG(
        POWER(model_probability - actual_selected_win, 2)
    ) FILTER (
        WHERE actual_selected_win IS NOT NULL
    )::NUMERIC(14,10) AS brier_score,
    AVG(
        CASE
            WHEN actual_selected_win = 1
                THEN -LN(model_probability)
            WHEN actual_selected_win = 0
                THEN -LN(1 - model_probability)
            ELSE NULL
        END
    )::NUMERIC(14,10) AS log_loss,
    CASE
        WHEN COUNT(*) FILTER (WHERE clv_status = 'AVAILABLE') = 0 THEN NULL
        ELSE AVG(clv_probability_delta) FILTER (
            WHERE clv_status = 'AVAILABLE'
        )::NUMERIC(14,10)
    END AS average_clv_probability_delta
FROM baseball_moneyline_evaluation_rows
GROUP BY bookmaker;

COMMIT;
