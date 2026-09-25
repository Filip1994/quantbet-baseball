-- QuantBet Baseball fixed paper stake and RSD research P/L
-- Migration: 008_paper_stake_rsd

BEGIN;

ALTER TABLE registered_picks
    ADD COLUMN IF NOT EXISTS paper_stake_minor BIGINT NOT NULL DEFAULT 30000;

ALTER TABLE registered_picks
    ADD COLUMN IF NOT EXISTS currency TEXT NOT NULL DEFAULT 'RSD';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'registered_picks_fixed_paper_stake'
    ) THEN
        ALTER TABLE registered_picks
            ADD CONSTRAINT registered_picks_fixed_paper_stake
            CHECK (paper_stake_minor = 30000);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'registered_picks_currency_rsd'
    ) THEN
        ALTER TABLE registered_picks
            ADD CONSTRAINT registered_picks_currency_rsd
            CHECK (currency = 'RSD');
    END IF;
END
$$;

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
    s.settled_at,
    r.paper_stake_minor,
    r.currency,
    CASE
        WHEN s.settlement_id IS NULL THEN NULL
        ELSE ROUND(s.profit_per_unit * r.paper_stake_minor)::BIGINT
    END AS paper_profit_minor
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
    )::NUMERIC(14,10) AS average_clv_price_ratio,
    COALESCE(
        SUM(paper_stake_minor) FILTER (WHERE settlement_id IS NOT NULL),
        0
    )::BIGINT AS settled_stake_minor,
    COALESCE(
        SUM(paper_profit_minor) FILTER (WHERE settlement_id IS NOT NULL),
        0
    )::BIGINT AS realized_profit_minor
FROM baseball_moneyline_pick_projection;

COMMIT;
