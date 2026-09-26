BEGIN;

CREATE TABLE IF NOT EXISTS official_mlb_team_identity_mappings (
    mapping_id UUID PRIMARY KEY,
    mapping_version TEXT NOT NULL,
    api_sports_team_id BIGINT NOT NULL,
    api_sports_team_name TEXT NOT NULL,
    official_mlb_team_id BIGINT NOT NULL,
    official_mlb_team_name TEXT NOT NULL,
    verified_at TIMESTAMPTZ NOT NULL,
    api_fixture_observation_id UUID NOT NULL,
    api_source_payload_ref TEXT NOT NULL,
    api_source_payload_checksum TEXT NOT NULL,
    mlb_schedule_source_payload_ref TEXT NOT NULL,
    mlb_schedule_source_payload_checksum TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    UNIQUE (mapping_version, api_sports_team_id),
    UNIQUE (mapping_version, official_mlb_team_id)
);

CREATE INDEX IF NOT EXISTS idx_official_mlb_team_identity_version
    ON official_mlb_team_identity_mappings (mapping_version, api_sports_team_id);

CREATE TABLE IF NOT EXISTS official_mlb_game_identity_links (
    link_id UUID PRIMARY KEY,
    mapping_version TEXT NOT NULL,
    game_id TEXT NOT NULL,
    api_sports_provider_game_id BIGINT NOT NULL,
    mlb_game_pk BIGINT NOT NULL,
    api_home_team_id BIGINT NOT NULL,
    api_away_team_id BIGINT NOT NULL,
    mlb_home_team_id BIGINT NOT NULL,
    mlb_away_team_id BIGINT NOT NULL,
    api_sports_first_pitch TIMESTAMPTZ NOT NULL,
    official_mlb_first_pitch TIMESTAMPTZ NOT NULL,
    kickoff_delta_seconds INTEGER NOT NULL CHECK (kickoff_delta_seconds >= 0),
    linked_at TIMESTAMPTZ NOT NULL,
    api_fixture_observation_id UUID NOT NULL,
    api_source_payload_ref TEXT NOT NULL,
    api_source_payload_checksum TEXT NOT NULL,
    mlb_schedule_source_payload_ref TEXT NOT NULL,
    mlb_schedule_source_payload_checksum TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    UNIQUE (mapping_version, api_sports_provider_game_id),
    UNIQUE (mapping_version, mlb_game_pk)
);

CREATE INDEX IF NOT EXISTS idx_official_mlb_game_identity_game
    ON official_mlb_game_identity_links (api_sports_provider_game_id, mapping_version);

COMMIT;
