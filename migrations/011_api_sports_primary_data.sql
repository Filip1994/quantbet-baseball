-- QuantBet Baseball API-Sports primary slow-moving provider evidence
-- Migration: 011_api_sports_primary_data

BEGIN;

CREATE TABLE IF NOT EXISTS api_sports_standing_snapshots (
    snapshot_id UUID PRIMARY KEY,
    provider TEXT NOT NULL,
    league_id BIGINT NOT NULL,
    season INTEGER NOT NULL,
    team_id BIGINT NOT NULL,
    team_name TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    games_played INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    losses INTEGER NOT NULL,
    win_percentage DOUBLE PRECISION NOT NULL,
    loss_percentage DOUBLE PRECISION NOT NULL,
    runs_for DOUBLE PRECISION NOT NULL,
    runs_against DOUBLE PRECISION NOT NULL,
    position INTEGER,
    stage TEXT,
    group_name TEXT,
    source_payload_ref TEXT NOT NULL,
    source_payload_checksum CHAR(64) NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT api_sports_standings_provider_valid
        CHECK (provider = 'api-sports-baseball'),
    CONSTRAINT api_sports_standings_identity_valid
        CHECK (league_id > 0 AND season >= 1900 AND team_id > 0),
    CONSTRAINT api_sports_standings_counts_valid
        CHECK (games_played >= 0 AND wins >= 0 AND losses >= 0),
    CONSTRAINT api_sports_standings_position_valid
        CHECK (position IS NULL OR position > 0),
    CONSTRAINT api_sports_standings_checksum_valid
        CHECK (source_payload_checksum ~ '^[0-9a-fA-F]{64}$'),
    CONSTRAINT api_sports_standings_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_api_sports_standings_team_time
    ON api_sports_standing_snapshots (
        league_id,
        season,
        team_id,
        observed_at DESC,
        snapshot_id
    );

CREATE INDEX IF NOT EXISTS idx_api_sports_standings_league_time
    ON api_sports_standing_snapshots (
        league_id,
        season,
        observed_at DESC,
        snapshot_id
    );

CREATE TABLE IF NOT EXISTS api_sports_team_statistics_snapshots (
    snapshot_id UUID PRIMARY KEY,
    provider TEXT NOT NULL,
    league_id BIGINT NOT NULL,
    season INTEGER NOT NULL,
    team_id BIGINT NOT NULL,
    team_name TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,

    games_played_all INTEGER NOT NULL,
    games_played_home INTEGER NOT NULL,
    games_played_away INTEGER NOT NULL,

    wins_all INTEGER NOT NULL,
    wins_home INTEGER NOT NULL,
    wins_away INTEGER NOT NULL,
    win_pct_all DOUBLE PRECISION NOT NULL,
    win_pct_home DOUBLE PRECISION NOT NULL,
    win_pct_away DOUBLE PRECISION NOT NULL,

    losses_all INTEGER NOT NULL,
    losses_home INTEGER NOT NULL,
    losses_away INTEGER NOT NULL,
    loss_pct_all DOUBLE PRECISION NOT NULL,
    loss_pct_home DOUBLE PRECISION NOT NULL,
    loss_pct_away DOUBLE PRECISION NOT NULL,

    runs_for_total_all DOUBLE PRECISION NOT NULL,
    runs_for_total_home DOUBLE PRECISION NOT NULL,
    runs_for_total_away DOUBLE PRECISION NOT NULL,
    runs_for_avg_all DOUBLE PRECISION NOT NULL,
    runs_for_avg_home DOUBLE PRECISION NOT NULL,
    runs_for_avg_away DOUBLE PRECISION NOT NULL,

    runs_against_total_all DOUBLE PRECISION NOT NULL,
    runs_against_total_home DOUBLE PRECISION NOT NULL,
    runs_against_total_away DOUBLE PRECISION NOT NULL,
    runs_against_avg_all DOUBLE PRECISION NOT NULL,
    runs_against_avg_home DOUBLE PRECISION NOT NULL,
    runs_against_avg_away DOUBLE PRECISION NOT NULL,

    source_payload_ref TEXT NOT NULL,
    source_payload_checksum CHAR(64) NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT api_sports_team_stats_provider_valid
        CHECK (provider = 'api-sports-baseball'),
    CONSTRAINT api_sports_team_stats_identity_valid
        CHECK (league_id > 0 AND season >= 1900 AND team_id > 0),
    CONSTRAINT api_sports_team_stats_counts_valid CHECK (
        games_played_all >= 0
        AND games_played_home >= 0
        AND games_played_away >= 0
        AND wins_all >= 0
        AND wins_home >= 0
        AND wins_away >= 0
        AND losses_all >= 0
        AND losses_home >= 0
        AND losses_away >= 0
    ),
    CONSTRAINT api_sports_team_stats_checksum_valid
        CHECK (source_payload_checksum ~ '^[0-9a-fA-F]{64}$'),
    CONSTRAINT api_sports_team_stats_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_api_sports_team_stats_team_time
    ON api_sports_team_statistics_snapshots (
        league_id,
        season,
        team_id,
        observed_at DESC,
        snapshot_id
    );

CREATE TABLE IF NOT EXISTS api_sports_reference_catalog_snapshots (
    snapshot_id UUID PRIMARY KEY,
    provider TEXT NOT NULL,
    catalog_type TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    source_payload_ref TEXT NOT NULL,
    source_payload_checksum CHAR(64) NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT api_sports_reference_provider_valid
        CHECK (provider = 'api-sports-baseball'),
    CONSTRAINT api_sports_reference_type_valid
        CHECK (catalog_type IN ('BET_TYPES', 'BOOKMAKERS')),
    CONSTRAINT api_sports_reference_checksum_valid
        CHECK (source_payload_checksum ~ '^[0-9a-fA-F]{64}$'),
    CONSTRAINT api_sports_reference_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_api_sports_reference_type_time
    ON api_sports_reference_catalog_snapshots (
        catalog_type,
        observed_at DESC,
        snapshot_id
    );

COMMIT;
