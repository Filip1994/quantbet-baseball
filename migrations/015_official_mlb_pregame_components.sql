-- QuantBet Baseball Official MLB component-level pregame evidence
-- Migration: 015_official_mlb_pregame_components

BEGIN;

CREATE TABLE IF NOT EXISTS official_mlb_starter_evidence (
    evidence_id UUID PRIMARY KEY,
    mlb_game_pk BIGINT NOT NULL,
    side TEXT NOT NULL,
    starter_state TEXT NOT NULL,
    pitcher_id BIGINT,
    pitcher_name TEXT,
    source_observed_at TIMESTAMPTZ NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    scheduled_first_pitch TIMESTAMPTZ NOT NULL,
    requested_timecode TEXT,
    source_payload_ref TEXT NOT NULL,
    source_payload_checksum CHAR(64) NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT official_mlb_starter_game_valid CHECK (mlb_game_pk > 0),
    CONSTRAINT official_mlb_starter_side_valid CHECK (side IN ('HOME', 'AWAY')),
    CONSTRAINT official_mlb_starter_state_valid
        CHECK (starter_state IN ('ABSENT', 'PROBABLE')),
    CONSTRAINT official_mlb_starter_identity_consistent CHECK (
        (
            starter_state = 'ABSENT'
            AND pitcher_id IS NULL
            AND pitcher_name IS NULL
        )
        OR
        (
            starter_state = 'PROBABLE'
            AND pitcher_id > 0
            AND length(btrim(pitcher_name)) > 0
        )
    ),
    CONSTRAINT official_mlb_starter_source_before_pitch
        CHECK (source_observed_at < scheduled_first_pitch),
    CONSTRAINT official_mlb_starter_retrieval_valid
        CHECK (retrieved_at >= source_observed_at),
    CONSTRAINT official_mlb_starter_checksum_valid
        CHECK (source_payload_checksum ~ '^[0-9a-fA-F]{64}$'),
    CONSTRAINT official_mlb_starter_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_official_mlb_starter_known_at
    ON official_mlb_starter_evidence (
        mlb_game_pk,
        side,
        retrieved_at DESC,
        source_observed_at DESC,
        evidence_id
    );

CREATE TABLE IF NOT EXISTS official_mlb_lineup_evidence (
    evidence_id UUID PRIMARY KEY,
    mlb_game_pk BIGINT NOT NULL,
    side TEXT NOT NULL,
    lineup_state TEXT NOT NULL,
    batting_order_ids BIGINT[] NOT NULL,
    confirmation_state TEXT NOT NULL,
    source_observed_at TIMESTAMPTZ NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    scheduled_first_pitch TIMESTAMPTZ NOT NULL,
    requested_timecode TEXT,
    source_payload_ref TEXT NOT NULL,
    source_payload_checksum CHAR(64) NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT official_mlb_lineup_game_valid CHECK (mlb_game_pk > 0),
    CONSTRAINT official_mlb_lineup_side_valid CHECK (side IN ('HOME', 'AWAY')),
    CONSTRAINT official_mlb_lineup_state_valid
        CHECK (lineup_state IN ('ABSENT', 'PARTIAL', 'POPULATED')),
    CONSTRAINT official_mlb_lineup_confirmation_valid
        CHECK (confirmation_state = 'NOT_ASSERTED'),
    CONSTRAINT official_mlb_lineup_state_count_consistent CHECK (
        (lineup_state = 'ABSENT' AND cardinality(batting_order_ids) = 0)
        OR
        (
            lineup_state = 'PARTIAL'
            AND cardinality(batting_order_ids) BETWEEN 1 AND 8
        )
        OR
        (lineup_state = 'POPULATED' AND cardinality(batting_order_ids) >= 9)
    ),
    CONSTRAINT official_mlb_lineup_player_ids_positive CHECK (
        NOT EXISTS (
            SELECT 1
            FROM unnest(batting_order_ids) AS player_id
            WHERE player_id <= 0
        )
    ),
    CONSTRAINT official_mlb_lineup_source_before_pitch
        CHECK (source_observed_at < scheduled_first_pitch),
    CONSTRAINT official_mlb_lineup_retrieval_valid
        CHECK (retrieved_at >= source_observed_at),
    CONSTRAINT official_mlb_lineup_checksum_valid
        CHECK (source_payload_checksum ~ '^[0-9a-fA-F]{64}$'),
    CONSTRAINT official_mlb_lineup_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_official_mlb_lineup_known_at
    ON official_mlb_lineup_evidence (
        mlb_game_pk,
        side,
        retrieved_at DESC,
        source_observed_at DESC,
        evidence_id
    );

COMMIT;
