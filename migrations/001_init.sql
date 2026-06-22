-- Core schema. Applied automatically by the postgres container on first boot.
-- Phase 1 persists to JSON/JSONL files; these tables are the Phase 2 target so
-- the audit trail, journal, and metrics move into PostgreSQL unchanged in shape.

CREATE TABLE IF NOT EXISTS decisions (
    id              SERIAL PRIMARY KEY,
    asset           TEXT        NOT NULL,
    action          TEXT        NOT NULL,           -- LONG | SHORT | FLAT
    conviction      NUMERIC     NOT NULL DEFAULT 0,
    allocation      NUMERIC     NOT NULL DEFAULT 0,
    entry           NUMERIC,
    stop_loss       NUMERIC,
    take_profit     NUMERIC,
    expected_value  NUMERIC,
    reward_risk     NUMERIC,
    rejected        BOOLEAN     NOT NULL DEFAULT FALSE,
    rejection_reason TEXT,
    regime          TEXT,
    consulted_agents JSONB,
    risk_flags      JSONB,
    learned_penalties JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_decisions_asset ON decisions (asset);
CREATE INDEX IF NOT EXISTS idx_decisions_created ON decisions (created_at);
