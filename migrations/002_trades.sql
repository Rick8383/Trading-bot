-- Closed trades + the post-mortem error tags used by the learning loop.

CREATE TABLE IF NOT EXISTS trades (
    id            SERIAL PRIMARY KEY,
    symbol        TEXT        NOT NULL,
    action        TEXT        NOT NULL,
    quantity      NUMERIC     NOT NULL,
    entry         NUMERIC     NOT NULL,
    exit          NUMERIC     NOT NULL,
    stop_loss     NUMERIC,
    take_profit   NUMERIC,
    pnl           NUMERIC     NOT NULL,
    return_pct    NUMERIC     NOT NULL,
    reason        TEXT,                              -- stop_loss | take_profit | ...
    conviction    NUMERIC,
    regime        TEXT,
    reward_risk   NUMERIC,
    risk_flags    JSONB,
    error_tags    JSONB,
    opened_at     TIMESTAMPTZ,
    closed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades (symbol);

-- Aggregated lessons (the knowledge base, mirrored from knowledge.json).
CREATE TABLE IF NOT EXISTS lessons (
    key         TEXT PRIMARY KEY,
    samples     INTEGER NOT NULL DEFAULT 0,
    wins        INTEGER NOT NULL DEFAULT 0,
    losses      INTEGER NOT NULL DEFAULT 0,
    pnl_sum     NUMERIC NOT NULL DEFAULT 0,
    description TEXT,
    remedy      TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
