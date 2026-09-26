-- QuantBet Baseball official MLB point-in-time pregame evidence
-- Migration: 010_official_mlb_pregame_snapshots

BEGIN;

CREATE TABLE IF NOT EXISTS official_mlb_pregame_snapshots (
    snapshot_id UUID PRIMARY KEY,
    mlb_game_pk BIGINT NOT NULL,
    provider TEXT NOT NULL,
    source_observed_at TIMESTAMPTZ NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    scheduled_first_pitch TIMESTAMPTZ NOT NULL,
    requested_timecode TEXT,
    status_abstract TEXT NOT NULL,
    status_detailed TEXT NOT NULL,
    away_team_id BIGINT NOT NULL,
    home_team_id BIGINT NOT NULL,
    away_probable_pitcher_id BIGINT,
    home_probable_pitcher_id BIGINT,
    away_lineup_count INTEGER NOT NULL,
    home_lineup_count INTEGER NOT NULL,
    lineup_state TEXT NOT NULL,
    venue_id BIGINT NOT NULL,
    source_payload_ref TEXT NOT NULL,
    source_payload_checksum CHAR(64) NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT official_mlb_pregame_provider_valid
        CHECK (provider = 'official-mlb-stats-api'),
    CONSTRAINT official_mlb_pregame_game_pk_valid CHECK (mlb_game_pk > 0),
    CONSTRAINT official_mlb_pregame_team_ids_valid
        CHECK (away_team_id > 0 AND home_team_id > 0 AND away_team_id <> home_team_id),
    CONSTRAINT official_mlb_pregame_pitcher_ids_valid CHECK (
        (away_probable_pitcher_id IS NULL OR away_probable_pitcher_id > 0)
        AND (home_probable_pitcher_id IS NULL OR home_probable_pitcher_id > 0)
    ),
    CONSTRAINT official_mlb_pregame_lineup_counts_valid
        CHECK (away_lineup_count >= 0 AND home_lineup_count >= 0),
    CONSTRAINT official_mlb_pregame_lineup_state_valid
        CHECK (lineup_state IN ('ABSENT', 'PARTIAL', 'POPULATED')),
    CONSTRAINT official_mlb_pregame_venue_valid CHECK (venue_id > 0),
    CONSTRAINT official_mlb_pregame_source_before_pitch
        CHECK (source_observed_at < scheduled_first_pitch),
    CONSTRAINT official_mlb_pregame_retrieval_valid
        CHECK (retrieved_at >= source_observed_at),
    CONSTRAINT official_mlb_pregame_checksum_valid
        CHECK (source_payload_checksum ~ '^[0-9a-fA-F]{64}$'),
    CONSTRAINT official_mlb_pregame_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_official_mlb_pregame_game_source_time
    ON official_mlb_pregame_snapshots (
        mlb_game_pk,
        source_observed_at DESC,
        snapshot_id
    );

CREATE INDEX IF NOT EXISTS idx_official_mlb_pregame_first_pitch
    ON official_mlb_pregame_snapshots (scheduled_first_pitch, mlb_game_pk);

COMMIT;
