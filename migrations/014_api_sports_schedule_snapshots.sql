BEGIN;

CREATE TABLE IF NOT EXISTS api_sports_game_schedule_snapshots (
    snapshot_id UUID PRIMARY KEY,
    snapshot_group_id UUID NOT NULL,
    provider TEXT NOT NULL,
    query_date DATE NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    response_rows INTEGER NOT NULL,
    provider_game_ids BIGINT[] NOT NULL,
    source_payload_ref TEXT NOT NULL,
    source_payload_checksum CHAR(64) NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT api_sports_schedule_snapshots_provider_valid
        CHECK (provider = 'api-sports-baseball'),
    CONSTRAINT api_sports_schedule_snapshots_rows_nonnegative
        CHECK (response_rows >= 0),
    CONSTRAINT api_sports_schedule_snapshots_membership_count_valid
        CHECK (response_rows >= cardinality(provider_game_ids)),
    CONSTRAINT api_sports_schedule_snapshots_checksum_valid
        CHECK (source_payload_checksum ~ '^[0-9a-fA-F]{64}$'),
    CONSTRAINT api_sports_schedule_snapshots_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object'),
    CONSTRAINT api_sports_schedule_snapshots_group_date_unique
        UNIQUE (snapshot_group_id, query_date)
);

CREATE INDEX IF NOT EXISTS idx_api_sports_schedule_snapshots_query_date
    ON api_sports_game_schedule_snapshots (
        query_date,
        observed_at DESC,
        snapshot_group_id
    );

CREATE INDEX IF NOT EXISTS idx_api_sports_schedule_snapshots_group
    ON api_sports_game_schedule_snapshots (snapshot_group_id, query_date);

COMMIT;
