-- QuantBet Baseball cold-storage archive manifests
-- Migration: 017_cold_storage_archives

BEGIN;

CREATE TABLE IF NOT EXISTS cold_storage_archives (
    archive_id UUID PRIMARY KEY,
    table_name TEXT NOT NULL,
    archive_mode TEXT NOT NULL,
    cutoff_at TIMESTAMPTZ NOT NULL,
    object_ref TEXT NOT NULL UNIQUE,
    object_sha256 CHAR(64) NOT NULL,
    object_bytes BIGINT NOT NULL,
    row_count INTEGER NOT NULL,
    first_record_at TIMESTAMPTZ,
    last_record_at TIMESTAMPTZ,
    archived_at TIMESTAMPTZ NOT NULL,
    purged_from_hot_at TIMESTAMPTZ NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,

    CONSTRAINT cold_storage_archives_table_valid CHECK (
        table_name IN (
            'api_sports_game_history_snapshots',
            'fixture_observations',
            'odds_observations',
            'odds_poll_attempts'
        )
    ),
    CONSTRAINT cold_storage_archives_mode_valid CHECK (
        archive_mode IN ('SUPERSEDED', 'SUPERSEDED_UNREFERENCED', 'UNREFERENCED', 'AGE')
    ),
    CONSTRAINT cold_storage_archives_checksum_valid CHECK (
        object_sha256 ~ '^[0-9a-fA-F]{64}$'
    ),
    CONSTRAINT cold_storage_archives_counts_valid CHECK (
        object_bytes > 0 AND row_count > 0
    ),
    CONSTRAINT cold_storage_archives_time_valid CHECK (
        purged_from_hot_at >= archived_at
    ),
    CONSTRAINT cold_storage_archives_record_object CHECK (
        jsonb_typeof(canonical_record) = 'object'
    )
);

CREATE INDEX IF NOT EXISTS idx_cold_storage_archives_table_time
    ON cold_storage_archives (table_name, archived_at DESC, archive_id DESC);

CREATE INDEX IF NOT EXISTS idx_cold_storage_archives_cutoff
    ON cold_storage_archives (cutoff_at, table_name);

COMMIT;
