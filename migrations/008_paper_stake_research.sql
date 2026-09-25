-- QuantBet Baseball fixed paper stake and RSD P/L projections
-- Migration: 008_paper_stake_research.sql

BEGIN;

ALTER TABLE registered_picks
    ADD COLUMN IF NOT EXISTS paper_stake_rsd INTEGER;

UPDATE registered_picks
SET paper_stake_rsd = 300
WHERE paper_stake_rsd IS NULL;

ALTER TABLE registered_picks
    ALTER COLUMN paper_stake_rsd SET DEFAULT 300,
    ALTER COLUMN paper_stake_rsd SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'registered_picks_paper_stake_positive'
    ) THEN
        ALTER TABLE registered_picks
            ADD CONSTRAINT registered_picks_paper_stake_positive
            CHECK (paper_stake_rsd > 0);
    END IF;
END $$;

ALTER TABLE pick_settlements
    ADD COLUMN IF NOT EXISTS paper_stake_rsd INTEGER,
    ADD COLUMN IF NOT EXISTS paper_profit_rsd NUMERIC(16,2);

UPDATE pick_settlements s
SET paper_stake_rsd = COALESCE(r.paper_stake_rsd, 300)
FROM registered_picks r
WHERE s.pick_id = r.pick_id
  AND s.paper_stake_rsd IS NULL;

UPDATE pick_settlements
SET paper_stake_rsd = 300
WHERE paper_stake_rsd IS NULL;

UPDATE pick_settlements
SET paper_profit_rsd = ROUND(profit_per_unit * paper_stake_rsd, 2)
WHERE paper_profit_rsd IS NULL;

ALTER TABLE pick_settlements
    ALTER COLUMN paper_stake_rsd SET DEFAULT 300,
    ALTER COLUMN paper_stake_rsd SET NOT NULL,
    ALTER COLUMN paper_profit_rsd SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'pick_settlements_paper_stake_positive'
    ) THEN
        ALTER TABLE pick_settlements
            ADD CONSTRAINT pick_settlements_paper_stake_positive
            CHECK (paper_stake_rsd > 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'pick_settlements_paper_profit_matches'
    ) THEN
        ALTER TABLE pick_settlements
            ADD CONSTRAINT pick_settlements_paper_profit_matches
            CHECK (
                ABS(
                    paper_profit_rsd
                    - ROUND(profit_per_unit * paper_stake_rsd, 2)
                ) <= 0.01
            );
    END IF;
END $$;

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
    r.paper_stake_rsd,
    s.paper_profit_rsd
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
    COALESCE(SUM(paper_profit_rsd), 0)::NUMERIC(18,2)
        AS realized_paper_profit_rsd,
    COALESCE(
        SUM(paper_stake_rsd) FILTER (WHERE settlement_id IS NOT NULL),
        0
    )::BIGINT AS total_paper_staked_rsd,
    CASE
        WHEN COALESCE(
            SUM(paper_stake_rsd) FILTER (WHERE settlement_id IS NOT NULL),
            0
        ) > 0
        THEN (
            COALESCE(SUM(paper_profit_rsd), 0)
            /
            SUM(paper_stake_rsd) FILTER (WHERE settlement_id IS NOT NULL)
        )::NUMERIC(14,10)
        ELSE NULL
    END AS paper_yield
FROM baseball_moneyline_pick_projection;

COMMIT;
