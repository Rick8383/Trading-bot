"""SQLite-backed durable store (stdlib sqlite3, no server required).

Tables mirror the PostgreSQL migrations. This gives the founder a real,
queryable history of every decision, closed trade, learned lesson and metric
snapshot — the audit trail and the learning memory persisted side by side.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from app.db.schema import SCHEMA
from app.learning.knowledge_base import Lesson
from app.learning.trade_journal import TradeRecord
from app.models import FinalDecision


class SQLiteStore:
    def __init__(self, path: str | Path = "data_store/trading.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    # --- writes --------------------------------------------------------
    def save_decision(self, d: FinalDecision) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """INSERT INTO decisions
                   (asset, action, conviction, allocation, entry, stop_loss, take_profit,
                    expected_value, reward_risk, rejected, rejection_reason, regime,
                    consulted_agents, risk_flags, learned_penalties, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    d.asset, d.action.value, d.conviction, d.allocation, d.entry, d.stop_loss,
                    d.take_profit, d.expected_value, d.reward_risk, int(d.rejected),
                    d.rejection_reason, d.regime.value if d.regime else None,
                    json.dumps(d.consulted_agents), json.dumps(d.risk_flags),
                    json.dumps(d.learned_penalties), d.timestamp.isoformat(),
                ),
            )
            conn.commit()

    def save_trade(self, r: TradeRecord) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """INSERT INTO trades
                   (symbol, action, quantity, entry, exit, stop_loss, take_profit, pnl,
                    return_pct, reason, conviction, regime, reward_risk, risk_flags,
                    error_tags, opened_at, closed_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    r.symbol, r.action, r.quantity, r.entry, r.exit, r.stop_loss, r.take_profit,
                    r.pnl, r.return_pct, r.reason, r.conviction, r.regime, r.reward_risk,
                    json.dumps(r.risk_flags), json.dumps(r.error_tags), r.opened_at, r.closed_at,
                ),
            )
            conn.commit()

    def upsert_lessons(self, lessons: dict[str, Lesson]) -> None:
        with closing(self._connect()) as conn:
            for key, l in lessons.items():
                conn.execute(
                    """INSERT INTO lessons (key, samples, wins, losses, pnl_sum, description, remedy, updated_at)
                       VALUES (?,?,?,?,?,?,?,?)
                       ON CONFLICT(key) DO UPDATE SET
                         samples=excluded.samples, wins=excluded.wins, losses=excluded.losses,
                         pnl_sum=excluded.pnl_sum, description=excluded.description,
                         remedy=excluded.remedy, updated_at=excluded.updated_at""",
                    (key, l.samples, l.wins, l.losses, l.pnl_sum, l.description, l.remedy,
                     l.updated_at or datetime.now(timezone.utc).isoformat()),
                )
            conn.commit()

    def save_metric(self, equity: float, drawdown: float, report) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """INSERT INTO metrics
                   (equity, drawdown, sharpe, sortino, profit_factor, calmar, max_drawdown,
                    win_rate, n_trades, snapshot_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (equity, drawdown, report.sharpe, report.sortino, report.profit_factor,
                 report.calmar, report.max_drawdown, report.win_rate, report.n_trades,
                 datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()

    # --- reads ---------------------------------------------------------
    def count(self, table: str) -> int:
        if table not in {"decisions", "trades", "lessons", "metrics"}:
            raise ValueError(f"unknown table: {table}")
        with closing(self._connect()) as conn:
            return conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]

    def load_lessons(self) -> dict[str, dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM lessons").fetchall()
            return {row["key"]: dict(row) for row in rows}

    def recent_trades(self, limit: int = 20) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def recent_decisions(self, limit: int = 20) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def metrics_history(self, limit: int = 200) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM metrics ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows][::-1]

    def latest_metric(self) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM metrics ORDER BY id DESC LIMIT 1").fetchone()
            return dict(row) if row else None

    def lessons_list(self) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM lessons ORDER BY samples DESC").fetchall()
            return [dict(r) for r in rows]
