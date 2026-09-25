-- QuantBet Baseball immutable point-in-time feature snapshots
-- Migration: 008_pregame_feature_snapshots

BEGIN;

CREATE TABLE IF NOT EXISTS pregame_feature_snapshots (
    feature_snapshot_id UUID PRIMARY KEY,
    game_id TEXT NOT NULL REFERENCES fixtures(game_id) ON DELETE RESTRICT,
    feature_set_version TEXT NOT NULL,
    source_data_cutoff_at TIMESTAMPTZ NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    kickoff_at TIMESTAMPTZ NOT NULL,
    features JSONB NOT NULL,
    sources JSONB NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pregame_feature_snapshots_time_valid CHECK (
        source_data_cutoff_at <= generated_at
        AND generated_at < kickoff_at
    ),
    CONSTRAINT pregame_feature_snapshots_features_object
        CHECK (jsonb_typeof(features) = 'object'),
    CONSTRAINT pregame_feature_snapshots_sources_array
        CHECK (jsonb_typeof(sources) = 'array' AND jsonb_array_length(sources) > 0),
    CONSTRAINT pregame_feature_snapshots_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_pregame_feature_snapshots_game_time
    ON pregame_feature_snapshots (
        game_id,
        source_data_cutoff_at DESC,
        feature_snapshot_id
    );

CREATE TRIGGER baseball_pregame_feature_snapshots_append_only
    BEFORE UPDATE OR DELETE ON pregame_feature_snapshots
    FOR EACH ROW EXECUTE FUNCTION reject_baseball_pick_lifecycle_fact_mutation();

COMMIT;
