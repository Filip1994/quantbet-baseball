-- QuantBet Baseball verified cold-storage archival metadata
-- Migration: 017_cold_archive_storage
-- Scope: archive manifests / daily run checkpoints / restore audit only.

BEGIN;

CREATE TABLE IF NOT EXISTS cold_archive_manifests (
    archive_id UUID PRIMARY KEY,
    dataset TEXT NOT NULL,
    source_table TEXT NOT NULL,
    object_ref TEXT NOT NULL UNIQUE,
    object_checksum CHAR(64) NOT NULL,
    archive_format TEXT NOT NULL,
    retention_cutoff_at TIMESTAMPTZ NOT NULL,
    min_event_at TIMESTAMPTZ NOT NULL,
    max_event_at TIMESTAMPTZ NOT NULL,
    row_count INTEGER NOT NULL,
    compressed_bytes BIGINT NOT NULL,
    exported_at TIMESTAMPTZ NOT NULL,
    verified_at TIMESTAMPTZ NOT NULL,
    purged_at TIMESTAMPTZ NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,

    CONSTRAINT cold_archive_dataset_nonempty CHECK (length(trim(dataset)) > 0),
    CONSTRAINT cold_archive_source_table_nonempty CHECK (
        length(trim(source_table)) > 0
    ),
    CONSTRAINT cold_archive_object_ref_nonempty CHECK (
        length(trim(object_ref)) > 0
    ),
    CONSTRAINT cold_archive_checksum_valid CHECK (
        object_checksum ~ '^[0-9a-fA-F]{64}$'
    ),
    CONSTRAINT cold_archive_format_valid CHECK (archive_format = 'jsonl.gz'),
    CONSTRAINT cold_archive_rows_positive CHECK (row_count > 0),
    CONSTRAINT cold_archive_bytes_positive CHECK (compressed_bytes > 0),
    CONSTRAINT cold_archive_event_range_valid CHECK (max_event_at >= min_event_at),
    CONSTRAINT cold_archive_times_valid CHECK (
        verified_at >= exported_at
        AND purged_at >= verified_at
    ),
    CONSTRAINT cold_archive_canonical_object CHECK (
        jsonb_typeof(canonical_record) = 'object'
    )
);

CREATE INDEX IF NOT EXISTS idx_cold_archive_dataset_time
    ON cold_archive_manifests (
        dataset,
        max_event_at DESC,
        archive_id
    );

CREATE INDEX IF NOT EXISTS idx_cold_archive_purged
    ON cold_archive_manifests (purged_at DESC, archive_id);

CREATE TABLE IF NOT EXISTS cold_archive_runs (
    run_date DATE PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    objects_written INTEGER NOT NULL,
    rows_purged INTEGER NOT NULL,
    compressed_bytes BIGINT NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,

    CONSTRAINT cold_archive_runs_status_valid CHECK (status = 'SUCCESS'),
    CONSTRAINT cold_archive_runs_time_valid CHECK (finished_at >= started_at),
    CONSTRAINT cold_archive_runs_counts_valid CHECK (
        objects_written >= 0
        AND rows_purged >= 0
        AND compressed_bytes >= 0
    ),
    CONSTRAINT cold_archive_runs_canonical_object CHECK (
        jsonb_typeof(canonical_record) = 'object'
    )
);

CREATE TABLE IF NOT EXISTS cold_archive_restore_events (
    restore_id UUID PRIMARY KEY,
    archive_id UUID NOT NULL
        REFERENCES cold_archive_manifests(archive_id) ON DELETE RESTRICT,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL,
    rows_inserted INTEGER NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,

    CONSTRAINT cold_archive_restore_time_valid CHECK (
        finished_at >= started_at
    ),
    CONSTRAINT cold_archive_restore_rows_nonnegative CHECK (
        rows_inserted >= 0
    ),
    CONSTRAINT cold_archive_restore_canonical_object CHECK (
        jsonb_typeof(canonical_record) = 'object'
    )
);

CREATE INDEX IF NOT EXISTS idx_cold_archive_restore_archive
    ON cold_archive_restore_events (
        archive_id,
        finished_at DESC,
        restore_id
    );

COMMIT;
