"""SQLite DDL mirroring migrations/*.sql (Postgres types mapped to SQLite).

SERIAL -> INTEGER PRIMARY KEY AUTOINCREMENT, JSONB -> TEXT, TIMESTAMPTZ -> TEXT.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    asset             TEXT NOT NULL,
    action            TEXT NOT NULL,
    conviction        REAL NOT NULL DEFAULT 0,
    allocation        REAL NOT NULL DEFAULT 0,
    entry             REAL,
    stop_loss         REAL,
    take_profit       REAL,
    expected_value    REAL,
    reward_risk       REAL,
    rejected          INTEGER NOT NULL DEFAULT 0,
    rejection_reason  TEXT,
    regime            TEXT,
    consulted_agents  TEXT,
    risk_flags        TEXT,
    learned_penalties TEXT,
    created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decisions_asset ON decisions (asset);

CREATE TABLE IF NOT EXISTS trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT NOT NULL,
    action      TEXT NOT NULL,
    quantity    REAL NOT NULL,
    entry       REAL NOT NULL,
    exit        REAL NOT NULL,
    stop_loss   REAL,
    take_profit REAL,
    pnl         REAL NOT NULL,
    return_pct  REAL NOT NULL,
    reason      TEXT,
    conviction  REAL,
    regime      TEXT,
    reward_risk REAL,
    risk_flags  TEXT,
    error_tags  TEXT,
    opened_at   TEXT,
    closed_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades (symbol);

CREATE TABLE IF NOT EXISTS lessons (
    key         TEXT PRIMARY KEY,
    samples     INTEGER NOT NULL DEFAULT 0,
    wins        INTEGER NOT NULL DEFAULT 0,
    losses      INTEGER NOT NULL DEFAULT 0,
    pnl_sum     REAL NOT NULL DEFAULT 0,
    description TEXT,
    remedy      TEXT,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS metrics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    equity        REAL NOT NULL,
    drawdown      REAL NOT NULL,
    sharpe        REAL,
    sortino       REAL,
    profit_factor REAL,
    calmar        REAL,
    max_drawdown  REAL,
    win_rate      REAL,
    n_trades      INTEGER,
    snapshot_at   TEXT NOT NULL
);
"""
