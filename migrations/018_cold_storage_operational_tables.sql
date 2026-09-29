-- Expand verified cold-storage coverage to operational exhaust.
-- Migration: 018_cold_storage_operational_tables

BEGIN;

ALTER TABLE cold_storage_archives
    DROP CONSTRAINT IF EXISTS cold_storage_archives_table_valid;

ALTER TABLE cold_storage_archives
    ADD CONSTRAINT cold_storage_archives_table_valid CHECK (
        table_name IN (
            'api_sports_game_history_snapshots',
            'fixture_observations',
            'odds_observations',
            'odds_poll_attempts',
            'runtime_cycles',
            'collection_cycles',
            'api_sports_game_schedule_snapshots'
        )
    );

COMMIT;
