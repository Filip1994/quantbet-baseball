-- QuantBet Baseball immutable point-in-time model feature snapshots
-- Migration: 016_feature_snapshots

BEGIN;

CREATE TABLE IF NOT EXISTS feature_snapshots (
    snapshot_id UUID PRIMARY KEY,
    game_id TEXT NOT NULL REFERENCES fixtures(game_id) ON DELETE RESTRICT,
    feature_version TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    source_data_cutoff_at TIMESTAMPTZ NOT NULL,
    kickoff_at TIMESTAMPTZ NOT NULL,
    schema_version TEXT NOT NULL,
    features JSONB NOT NULL,
    sources JSONB NOT NULL,
    null_reasons JSONB NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT feature_snapshots_cutoff_valid
        CHECK (source_data_cutoff_at <= generated_at),
    CONSTRAINT feature_snapshots_before_kickoff
        CHECK (generated_at < kickoff_at),
    CONSTRAINT feature_snapshots_features_object
        CHECK (jsonb_typeof(features) = 'object'),
    CONSTRAINT feature_snapshots_sources_array
        CHECK (jsonb_typeof(sources) = 'array' AND jsonb_array_length(sources) > 0),
    CONSTRAINT feature_snapshots_null_reasons_object
        CHECK (jsonb_typeof(null_reasons) = 'object'),
    CONSTRAINT feature_snapshots_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_feature_snapshots_game_generated
    ON feature_snapshots (
        game_id,
        generated_at DESC,
        source_data_cutoff_at DESC,
        snapshot_id DESC
    );

CREATE INDEX IF NOT EXISTS idx_feature_snapshots_version_generated
    ON feature_snapshots (
        feature_version,
        generated_at DESC,
        snapshot_id DESC
    );

COMMIT;
