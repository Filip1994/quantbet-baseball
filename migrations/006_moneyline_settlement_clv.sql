-- QuantBet Baseball authoritative results, settlement and CLV read models
-- Migration: 006_moneyline_settlement_clv

BEGIN;

CREATE TABLE IF NOT EXISTS game_result_facts (
    result_id UUID PRIMARY KEY,
    game_id TEXT NOT NULL REFERENCES fixtures(game_id) ON DELETE RESTRICT,
    fixture_observation_id UUID NOT NULL UNIQUE
        REFERENCES fixture_observations(fixture_observation_id) ON DELETE RESTRICT,
    provider_status TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    home_score INTEGER NOT NULL,
    away_score INTEGER NOT NULL,
    winner TEXT NOT NULL,
    source_payload_ref TEXT NOT NULL,
    source_payload_checksum TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT game_result_facts_scores_valid
        CHECK (home_score >= 0 AND away_score >= 0),
    CONSTRAINT game_result_facts_winner_valid
        CHECK (winner IN ('home', 'away', 'tie')),
    CONSTRAINT game_result_facts_winner_shape CHECK (
        (winner = 'home' AND home_score > away_score)
        OR (winner = 'away' AND away_score > home_score)
        OR (winner = 'tie' AND home_score = away_score)
    ),
    CONSTRAINT game_result_facts_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_game_result_facts_game_observed
    ON game_result_facts (game_id, observed_at DESC, result_id DESC);

CREATE TABLE IF NOT EXISTS pick_settlements (
    settlement_id UUID PRIMARY KEY,
    pick_id UUID NOT NULL UNIQUE
        REFERENCES registered_picks(pick_id) ON DELETE RESTRICT,
    game_id TEXT NOT NULL REFERENCES fixtures(game_id) ON DELETE RESTRICT,
    result_id UUID NOT NULL
        REFERENCES game_result_facts(result_id) ON DELETE RESTRICT,
    closing_finalization_id UUID NOT NULL
        REFERENCES pick_closing_finalizations(finalization_id) ON DELETE RESTRICT,
    selection TEXT NOT NULL,
    entry_odds NUMERIC(10,5) NOT NULL,
    settled_at TIMESTAMPTZ NOT NULL,
    outcome TEXT NOT NULL,
    profit_per_unit NUMERIC(14,8) NOT NULL,
    closing_outcome TEXT NOT NULL,
    closing_observation_id UUID
        REFERENCES odds_observations(observation_id) ON DELETE RESTRICT,
    closing_odds NUMERIC(10,5),
    closing_market_probability NUMERIC(12,10),
    clv_probability_delta NUMERIC(12,10),
    clv_price_ratio NUMERIC(14,10),
    clv_status TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    canonical_record JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pick_settlements_selection_valid
        CHECK (selection IN ('home', 'away')),
    CONSTRAINT pick_settlements_entry_odds_valid
        CHECK (entry_odds > 1.0),
    CONSTRAINT pick_settlements_outcome_valid
        CHECK (outcome IN ('WIN', 'LOSS', 'PUSH')),
    CONSTRAINT pick_settlements_profit_shape CHECK (
        (outcome = 'WIN' AND profit_per_unit = entry_odds - 1.0)
        OR (outcome = 'LOSS' AND profit_per_unit = -1.0)
        OR (outcome = 'PUSH' AND profit_per_unit = 0.0)
    ),
    CONSTRAINT pick_settlements_closing_outcome_valid
        CHECK (closing_outcome IN ('CAPTURED', 'STALE_QUOTE', 'NO_VALID_QUOTE')),
    CONSTRAINT pick_settlements_clv_status_valid
        CHECK (
            clv_status IN (
                'AVAILABLE',
                'UNAVAILABLE_STALE_QUOTE',
                'UNAVAILABLE_NO_VALID_QUOTE'
            )
        ),
    CONSTRAINT pick_settlements_clv_shape CHECK (
        (
            clv_status = 'AVAILABLE'
            AND closing_outcome = 'CAPTURED'
            AND closing_observation_id IS NOT NULL
            AND closing_odds IS NOT NULL
            AND closing_odds > 1.0
            AND closing_market_probability IS NOT NULL
            AND closing_market_probability > 0
            AND closing_market_probability < 1
            AND clv_probability_delta IS NOT NULL
            AND clv_price_ratio IS NOT NULL
        )
        OR
        (
            clv_status = 'UNAVAILABLE_STALE_QUOTE'
            AND closing_outcome = 'STALE_QUOTE'
            AND closing_observation_id IS NULL
            AND closing_odds IS NULL
            AND closing_market_probability IS NULL
            AND clv_probability_delta IS NULL
            AND clv_price_ratio IS NULL
        )
        OR
        (
            clv_status = 'UNAVAILABLE_NO_VALID_QUOTE'
            AND closing_outcome = 'NO_VALID_QUOTE'
            AND closing_observation_id IS NULL
            AND closing_odds IS NULL
            AND closing_market_probability IS NULL
            AND clv_probability_delta IS NULL
            AND clv_price_ratio IS NULL
        )
    ),
    CONSTRAINT pick_settlements_canonical_object
        CHECK (jsonb_typeof(canonical_record) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_pick_settlements_settled
    ON pick_settlements (settled_at, pick_id);

CREATE TRIGGER baseball_game_result_facts_append_only
    BEFORE UPDATE OR DELETE ON game_result_facts
    FOR EACH ROW EXECUTE FUNCTION reject_baseball_pick_lifecycle_fact_mutation();

CREATE TRIGGER baseball_pick_settlements_immutable
    BEFORE UPDATE OR DELETE ON pick_settlements
    FOR EACH ROW EXECUTE FUNCTION reject_baseball_pick_lifecycle_fact_mutation();

CREATE OR REPLACE VIEW baseball_moneyline_pick_projection AS
SELECT
    r.pick_id,
    r.game_id,
    r.selection,
    r.bookmaker,
    r.entry_odds,
    r.market_probability AS entry_market_probability,
    r.registered_at,
    r.kickoff_at,
    COALESCE(m.state, 'REGISTERED') AS lifecycle_state,
    c.finalization_id AS closing_finalization_id,
    c.outcome AS closing_outcome,
    c.closing_observation_id,
    c.finalized_at AS closing_finalized_at,
    s.settlement_id,
    s.result_id,
    s.outcome AS settlement_outcome,
    s.profit_per_unit,
    s.clv_status,
    s.closing_odds,
    s.closing_market_probability,
    s.clv_probability_delta,
    s.clv_price_ratio,
    s.settled_at
FROM registered_picks r
LEFT JOIN pick_monitoring_states m ON m.pick_id = r.pick_id
LEFT JOIN pick_closing_finalizations c ON c.pick_id = r.pick_id
LEFT JOIN pick_settlements s ON s.pick_id = r.pick_id;

CREATE OR REPLACE VIEW baseball_moneyline_dashboard AS
SELECT
    COUNT(*)::BIGINT AS registered_picks,
    COUNT(closing_finalization_id)::BIGINT AS closing_finalizations,
    COUNT(settlement_id)::BIGINT AS settled_picks,
    COUNT(*) FILTER (
        WHERE closing_finalization_id IS NOT NULL AND settlement_id IS NULL
    )::BIGINT AS pending_settlement,
    COUNT(*) FILTER (WHERE settlement_outcome = 'WIN')::BIGINT AS wins,
    COUNT(*) FILTER (WHERE settlement_outcome = 'LOSS')::BIGINT AS losses,
    COUNT(*) FILTER (WHERE settlement_outcome = 'PUSH')::BIGINT AS pushes,
    COALESCE(SUM(profit_per_unit), 0)::NUMERIC(18,8) AS realized_profit_per_unit,
    COUNT(*) FILTER (WHERE clv_status = 'AVAILABLE')::BIGINT AS clv_available,
    COUNT(*) FILTER (
        WHERE clv_status IN (
            'UNAVAILABLE_STALE_QUOTE',
            'UNAVAILABLE_NO_VALID_QUOTE'
        )
    )::BIGINT AS clv_unavailable,
    AVG(clv_probability_delta) FILTER (
        WHERE clv_status = 'AVAILABLE'
    )::NUMERIC(12,10) AS average_clv_probability_delta,
    AVG(clv_price_ratio) FILTER (
        WHERE clv_status = 'AVAILABLE'
    )::NUMERIC(14,10) AS average_clv_price_ratio
FROM baseball_moneyline_pick_projection;

COMMIT;
