-- QuantBet Baseball Railway runtime invocation telemetry
-- Migration: 003_runtime_invocations

BEGIN;

CREATE TABLE IF NOT EXISTS runtime_cycles (
    run_id UUID PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL,
    collection_enabled BOOLEAN NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    stats JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT runtime_cycles_time_valid CHECK (finished_at >= started_at),
    CONSTRAINT runtime_cycles_mode_valid
        CHECK (mode IN ('storage-ready', 'collection')),
    CONSTRAINT runtime_cycles_status_nonempty
        CHECK (length(trim(status)) > 0),
    CONSTRAINT runtime_cycles_stats_object
        CHECK (jsonb_typeof(stats) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_runtime_cycles_finished
    ON runtime_cycles (finished_at DESC, run_id DESC);

COMMIT;
