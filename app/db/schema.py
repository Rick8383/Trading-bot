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

# PostgreSQL variant (SERIAL, JSONB, TIMESTAMPTZ). Mirrors migrations/*.sql.
SCHEMA_PG = """
CREATE TABLE IF NOT EXISTS decisions (
    id                SERIAL PRIMARY KEY,
    asset             TEXT NOT NULL,
    action            TEXT NOT NULL,
    conviction        DOUBLE PRECISION NOT NULL DEFAULT 0,
    allocation        DOUBLE PRECISION NOT NULL DEFAULT 0,
    entry             DOUBLE PRECISION,
    stop_loss         DOUBLE PRECISION,
    take_profit       DOUBLE PRECISION,
    expected_value    DOUBLE PRECISION,
    reward_risk       DOUBLE PRECISION,
    rejected          BOOLEAN NOT NULL DEFAULT FALSE,
    rejection_reason  TEXT,
    regime            TEXT,
    consulted_agents  JSONB,
    risk_flags        JSONB,
    learned_penalties JSONB,
    created_at        TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decisions_asset ON decisions (asset);

CREATE TABLE IF NOT EXISTS trades (
    id          SERIAL PRIMARY KEY,
    symbol      TEXT NOT NULL,
    action      TEXT NOT NULL,
    quantity    DOUBLE PRECISION NOT NULL,
    entry       DOUBLE PRECISION NOT NULL,
    exit        DOUBLE PRECISION NOT NULL,
    stop_loss   DOUBLE PRECISION,
    take_profit DOUBLE PRECISION,
    pnl         DOUBLE PRECISION NOT NULL,
    return_pct  DOUBLE PRECISION NOT NULL,
    reason      TEXT,
    conviction  DOUBLE PRECISION,
    regime      TEXT,
    reward_risk DOUBLE PRECISION,
    risk_flags  JSONB,
    error_tags  JSONB,
    opened_at   TIMESTAMPTZ,
    closed_at   TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades (symbol);

CREATE TABLE IF NOT EXISTS lessons (
    key         TEXT PRIMARY KEY,
    samples     INTEGER NOT NULL DEFAULT 0,
    wins        INTEGER NOT NULL DEFAULT 0,
    losses      INTEGER NOT NULL DEFAULT 0,
    pnl_sum     DOUBLE PRECISION NOT NULL DEFAULT 0,
    description TEXT,
    remedy      TEXT,
    updated_at  TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS metrics (
    id            SERIAL PRIMARY KEY,
    equity        DOUBLE PRECISION NOT NULL,
    drawdown      DOUBLE PRECISION NOT NULL,
    sharpe        DOUBLE PRECISION,
    sortino       DOUBLE PRECISION,
    profit_factor DOUBLE PRECISION,
    calmar        DOUBLE PRECISION,
    max_drawdown  DOUBLE PRECISION,
    win_rate      DOUBLE PRECISION,
    n_trades      INTEGER,
    snapshot_at   TIMESTAMPTZ NOT NULL
);
"""

