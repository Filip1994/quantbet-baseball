-- QuantBet Baseball successful odds poll-attempt evidence
-- Migration: 009_odds_poll_attempts
-- Purpose: throttle successful empty provider responses without fabricating quotes.

BEGIN;

CREATE TABLE IF NOT EXISTS odds_poll_attempts (
    poll_attempt_id UUID PRIMARY KEY,
    game_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_game_id BIGINT NOT NULL,
    attempted_at TIMESTAMPTZ NOT NULL,
    kickoff_at TIMESTAMPTZ NOT NULL,
    response_rows INTEGER NOT NULL,
    raw_market_rows INTEGER NOT NULL,
    canonical_rows INTEGER NOT NULL,
    source_payload_ref TEXT NOT NULL,
    source_payload_checksum CHAR(64) NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT odds_poll_attempts_provider_valid
        CHECK (provider = 'api-sports-baseball'),
    CONSTRAINT odds_poll_attempts_provider_game_id_valid
        CHECK (provider_game_id > 0),
    CONSTRAINT odds_poll_attempts_before_kickoff
        CHECK (attempted_at < kickoff_at),
    CONSTRAINT odds_poll_attempts_counts_valid
        CHECK (response_rows >= 0 AND raw_market_rows >= 0 AND canonical_rows >= 0),
    CONSTRAINT odds_poll_attempts_checksum_valid
        CHECK (source_payload_checksum ~ '^[0-9a-fA-F]{64}$'),
    CONSTRAINT odds_poll_attempts_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_odds_poll_attempts_game_time
    ON odds_poll_attempts (game_id, attempted_at DESC);

COMMIT;
