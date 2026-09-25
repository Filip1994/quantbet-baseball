-- QuantBet Baseball fixture evidence and runtime telemetry
-- Migration: 002_fixture_runtime_evidence

BEGIN;

CREATE TABLE IF NOT EXISTS fixtures (
    game_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    provider_game_id BIGINT NOT NULL,
    home_team_id BIGINT NOT NULL,
    away_team_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fixtures_provider_valid CHECK (provider = 'api-sports-baseball'),
    CONSTRAINT fixtures_provider_game_id_valid CHECK (provider_game_id > 0),
    CONSTRAINT fixtures_home_team_id_valid CHECK (home_team_id > 0),
    CONSTRAINT fixtures_away_team_id_valid CHECK (away_team_id > 0),
    CONSTRAINT fixtures_teams_differ CHECK (home_team_id <> away_team_id),
    CONSTRAINT fixtures_provider_identity_unique UNIQUE (provider, provider_game_id),
    CONSTRAINT fixtures_full_identity_unique
        UNIQUE (game_id, provider_game_id, home_team_id, away_team_id)
);

CREATE TABLE IF NOT EXISTS fixture_observations (
    fixture_observation_id UUID PRIMARY KEY,
    game_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_game_id BIGINT NOT NULL,
    league TEXT NOT NULL,
    home_team_id BIGINT NOT NULL,
    home_team_name TEXT NOT NULL,
    away_team_id BIGINT NOT NULL,
    away_team_name TEXT NOT NULL,
    kickoff_at TIMESTAMPTZ NOT NULL,
    provider_status TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    source_payload_ref TEXT NOT NULL,
    source_payload_checksum CHAR(64) NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fixture_observations_provider_valid
        CHECK (provider = 'api-sports-baseball'),
    CONSTRAINT fixture_observations_checksum_valid
        CHECK (source_payload_checksum ~ '^[0-9a-fA-F]{64}$'),
    CONSTRAINT fixture_observations_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object'),
    CONSTRAINT fixture_observations_fixture_identity_fk
        FOREIGN KEY (game_id, provider_game_id, home_team_id, away_team_id)
        REFERENCES fixtures (
            game_id, provider_game_id, home_team_id, away_team_id
        ) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_fixture_observations_game_time
    ON fixture_observations (game_id, observed_at, fixture_observation_id);

CREATE INDEX IF NOT EXISTS idx_fixture_observations_kickoff
    ON fixture_observations (kickoff_at, game_id);

CREATE TABLE IF NOT EXISTS collection_cycles (
    cycle_id UUID PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    games_seen INTEGER NOT NULL,
    fixture_observations_inserted INTEGER NOT NULL,
    pregame_games INTEGER NOT NULL,
    due_events INTEGER NOT NULL,
    games_selected INTEGER NOT NULL,
    odds_calls INTEGER NOT NULL,
    raw_market_rows INTEGER NOT NULL,
    canonical_rows INTEGER NOT NULL,
    observations_inserted INTEGER NOT NULL,
    api_requests INTEGER NOT NULL,
    api_remaining INTEGER NOT NULL,
    errors INTEGER NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT collection_cycles_status_valid
        CHECK (status IN ('collected', 'skipped_locked')),
    CONSTRAINT collection_cycles_time_valid CHECK (finished_at >= started_at),
    CONSTRAINT collection_cycles_counts_nonnegative CHECK (
        games_seen >= 0
        AND fixture_observations_inserted >= 0
        AND pregame_games >= 0
        AND due_events >= 0
        AND games_selected >= 0
        AND odds_calls >= 0
        AND raw_market_rows >= 0
        AND canonical_rows >= 0
        AND observations_inserted >= 0
        AND api_requests >= 0
        AND api_remaining >= 0
        AND errors >= 0
    ),
    CONSTRAINT collection_cycles_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_collection_cycles_finished
    ON collection_cycles (finished_at DESC, cycle_id);

COMMIT;
