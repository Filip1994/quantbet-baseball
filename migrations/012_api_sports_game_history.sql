-- QuantBet Baseball API-Sports canonical game-history snapshots
-- Migration: 012_api_sports_game_history

BEGIN;

CREATE TABLE IF NOT EXISTS api_sports_game_history_snapshots (
    snapshot_id UUID PRIMARY KEY,
    provider TEXT NOT NULL,
    provider_game_id BIGINT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    scheduled_first_pitch TIMESTAMPTZ NOT NULL,
    provider_timezone TEXT NOT NULL,
    status_long TEXT NOT NULL,
    status_short TEXT NOT NULL,
    league_id BIGINT NOT NULL,
    season INTEGER NOT NULL,
    home_team_id BIGINT NOT NULL,
    home_team_name TEXT NOT NULL,
    away_team_id BIGINT NOT NULL,
    away_team_name TEXT NOT NULL,
    home_score INTEGER,
    away_score INTEGER,
    home_hits INTEGER,
    away_hits INTEGER,
    home_errors INTEGER,
    away_errors INTEGER,
    home_innings JSONB NOT NULL,
    away_innings JSONB NOT NULL,
    source_payload_ref TEXT NOT NULL,
    source_payload_checksum CHAR(64) NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT api_sports_game_history_provider_valid
        CHECK (provider = 'api-sports-baseball'),
    CONSTRAINT api_sports_game_history_identity_valid CHECK (
        provider_game_id > 0
        AND league_id > 0
        AND season >= 1900
        AND home_team_id > 0
        AND away_team_id > 0
        AND home_team_id <> away_team_id
    ),
    CONSTRAINT api_sports_game_history_scores_valid CHECK (
        (home_score IS NULL OR home_score >= 0)
        AND (away_score IS NULL OR away_score >= 0)
        AND (home_hits IS NULL OR home_hits >= 0)
        AND (away_hits IS NULL OR away_hits >= 0)
        AND (home_errors IS NULL OR home_errors >= 0)
        AND (away_errors IS NULL OR away_errors >= 0)
    ),
    CONSTRAINT api_sports_game_history_home_innings_object
        CHECK (jsonb_typeof(home_innings) = 'object'),
    CONSTRAINT api_sports_game_history_away_innings_object
        CHECK (jsonb_typeof(away_innings) = 'object'),
    CONSTRAINT api_sports_game_history_checksum_valid
        CHECK (source_payload_checksum ~ '^[0-9a-fA-F]{64}$'),
    CONSTRAINT api_sports_game_history_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_api_sports_game_history_game_time
    ON api_sports_game_history_snapshots (
        provider_game_id,
        observed_at DESC,
        snapshot_id
    );

CREATE INDEX IF NOT EXISTS idx_api_sports_game_history_league_season_time
    ON api_sports_game_history_snapshots (
        league_id,
        season,
        scheduled_first_pitch,
        provider_game_id,
        observed_at DESC
    );

CREATE INDEX IF NOT EXISTS idx_api_sports_game_history_home_team
    ON api_sports_game_history_snapshots (
        home_team_id,
        scheduled_first_pitch,
        observed_at DESC
    );

CREATE INDEX IF NOT EXISTS idx_api_sports_game_history_away_team
    ON api_sports_game_history_snapshots (
        away_team_id,
        scheduled_first_pitch,
        observed_at DESC
    );

COMMIT;
