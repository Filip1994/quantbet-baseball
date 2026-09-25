-- QuantBet Baseball operational evidence and runtime telemetry
-- Migration: 002_operational_evidence

BEGIN;

CREATE TABLE IF NOT EXISTS fixture_observations (
    fixture_observation_id UUID PRIMARY KEY,
    game_id TEXT NOT NULL,
    league TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    kickoff_at TIMESTAMPTZ NOT NULL,
    provider_status TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    source_payload_ref TEXT NOT NULL,
    source_payload_checksum CHAR(64) NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fixture_observations_checksum_valid
        CHECK (source_payload_checksum ~ '^[0-9a-fA-F]{64}$'),
    CONSTRAINT fixture_observations_teams_distinct
        CHECK (home_team <> away_team),
    CONSTRAINT fixture_observations_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_fixture_observations_game_time
    ON fixture_observations (game_id, observed_at, fixture_observation_id);

CREATE INDEX IF NOT EXISTS idx_fixture_observations_kickoff
    ON fixture_observations (kickoff_at, game_id);

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
