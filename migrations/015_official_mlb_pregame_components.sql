-- QuantBet Baseball component-level Official MLB point-in-time evidence
-- Migration: 015_official_mlb_pregame_components

BEGIN;

CREATE TABLE IF NOT EXISTS official_mlb_pregame_components (
    component_id UUID PRIMARY KEY,
    mlb_game_pk BIGINT NOT NULL,
    provider TEXT NOT NULL,
    component_type TEXT NOT NULL,
    side TEXT NOT NULL,
    state TEXT NOT NULL,
    source_observed_at TIMESTAMPTZ NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    scheduled_first_pitch TIMESTAMPTZ NOT NULL,
    requested_timecode TEXT,
    source_payload_ref TEXT NOT NULL,
    source_payload_checksum CHAR(64) NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT official_mlb_component_provider_valid
        CHECK (provider = 'official-mlb-stats-api'),
    CONSTRAINT official_mlb_component_game_pk_valid CHECK (mlb_game_pk > 0),
    CONSTRAINT official_mlb_component_type_valid
        CHECK (component_type IN ('STARTER', 'LINEUP', 'BULLPEN', 'VENUE')),
    CONSTRAINT official_mlb_component_side_valid CHECK (
        (component_type IN ('STARTER', 'LINEUP', 'BULLPEN') AND side IN ('AWAY', 'HOME'))
        OR (component_type = 'VENUE' AND side = 'GAME')
    ),
    CONSTRAINT official_mlb_component_state_valid CHECK (
        (component_type = 'STARTER' AND state IN ('ABSENT', 'PROBABLE', 'CONFIRMED'))
        OR (component_type = 'LINEUP' AND state IN ('ABSENT', 'PARTIAL', 'POPULATED'))
        OR (component_type = 'BULLPEN' AND state IN ('ABSENT', 'PRESENT'))
        OR (component_type = 'VENUE' AND state = 'PRESENT')
    ),
    CONSTRAINT official_mlb_component_source_before_pitch
        CHECK (source_observed_at < scheduled_first_pitch),
    CONSTRAINT official_mlb_component_retrieval_valid
        CHECK (retrieved_at >= source_observed_at),
    CONSTRAINT official_mlb_component_checksum_valid
        CHECK (source_payload_checksum ~ '^[0-9a-fA-F]{64}$'),
    CONSTRAINT official_mlb_component_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_official_mlb_component_game_type_side_time
    ON official_mlb_pregame_components (
        mlb_game_pk,
        component_type,
        side,
        source_observed_at DESC,
        component_id
    );

CREATE INDEX IF NOT EXISTS idx_official_mlb_component_first_pitch
    ON official_mlb_pregame_components (
        scheduled_first_pitch,
        mlb_game_pk
    );

COMMIT;
