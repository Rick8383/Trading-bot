-- Periodic performance snapshots for the dashboard / monitoring.

CREATE TABLE IF NOT EXISTS metrics (
    id             SERIAL PRIMARY KEY,
    equity         NUMERIC     NOT NULL,
    drawdown       NUMERIC     NOT NULL,
    sharpe         NUMERIC,
    sortino        NUMERIC,
    profit_factor  NUMERIC,
    calmar         NUMERIC,
    max_drawdown   NUMERIC,
    win_rate       NUMERIC,
    n_trades       INTEGER,
    snapshot_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_metrics_snapshot ON metrics (snapshot_at);
