"""PostgreSQL-backed store — same interface as SQLiteStore.

Production persistence. ``psycopg`` (v3) is an optional dependency; importing
this module without it raises a clear error. The method surface is identical to
SQLiteStore so callers (session, runner, API) are storage-agnostic.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.db.schema import SCHEMA_PG
from app.learning.knowledge_base import Lesson
from app.learning.trade_journal import TradeRecord
from app.models import FinalDecision


class PostgresStore:
    def __init__(self, dsn: str):
        try:
            import psycopg  # psycopg v3
        except Exception as exc:  # pragma: no cover - environment dependent
            raise ImportError(
                "PostgresStore requires psycopg: pip install 'psycopg[binary]'"
            ) from exc
        self._psycopg = psycopg
        self.dsn = dsn
        self._init_schema()

    def _conn(self):
        return self._psycopg.connect(self.dsn, autocommit=True)

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.execute(SCHEMA_PG)

    # --- writes --------------------------------------------------------
    def save_decision(self, d: FinalDecision) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO decisions
                   (asset, action, conviction, allocation, entry, stop_loss, take_profit,
                    expected_value, reward_risk, rejected, rejection_reason, regime,
                    consulted_agents, risk_flags, learned_penalties, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (d.asset, d.action.value, d.conviction, d.allocation, d.entry, d.stop_loss,
                 d.take_profit, d.expected_value, d.reward_risk, d.rejected, d.rejection_reason,
                 d.regime.value if d.regime else None, json.dumps(d.consulted_agents),
                 json.dumps(d.risk_flags), json.dumps(d.learned_penalties), d.timestamp.isoformat()),
            )

    def save_trade(self, r: TradeRecord) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO trades
                   (symbol, action, quantity, entry, exit, stop_loss, take_profit, pnl,
                    return_pct, reason, conviction, regime, reward_risk, risk_flags,
                    error_tags, opened_at, closed_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (r.symbol, r.action, r.quantity, r.entry, r.exit, r.stop_loss, r.take_profit,
                 r.pnl, r.return_pct, r.reason, r.conviction, r.regime, r.reward_risk,
                 json.dumps(r.risk_flags), json.dumps(r.error_tags),
                 r.opened_at or None, r.closed_at),
            )

    def upsert_lessons(self, lessons: dict[str, Lesson]) -> None:
        with self._conn() as conn:
            for key, l in lessons.items():
                conn.execute(
                    """INSERT INTO lessons (key, samples, wins, losses, pnl_sum, description, remedy, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (key) DO UPDATE SET
                         samples=EXCLUDED.samples, wins=EXCLUDED.wins, losses=EXCLUDED.losses,
                         pnl_sum=EXCLUDED.pnl_sum, description=EXCLUDED.description,
                         remedy=EXCLUDED.remedy, updated_at=EXCLUDED.updated_at""",
                    (key, l.samples, l.wins, l.losses, l.pnl_sum, l.description, l.remedy,
                     l.updated_at or datetime.now(timezone.utc).isoformat()),
                )

    def save_metric(self, equity: float, drawdown: float, report) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO metrics
                   (equity, drawdown, sharpe, sortino, profit_factor, calmar, max_drawdown,
                    win_rate, n_trades, snapshot_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (equity, drawdown, report.sharpe, report.sortino, report.profit_factor,
                 report.calmar, report.max_drawdown, report.win_rate, report.n_trades,
                 datetime.now(timezone.utc).isoformat()),
            )

    # --- reads ---------------------------------------------------------
    def _rows(self, sql: str, params=()) -> list[dict]:
        with self._conn() as conn:
            cur = conn.execute(sql, params)
            cols = [c.name for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def count(self, table: str) -> int:
        if table not in {"decisions", "trades", "lessons", "metrics"}:
            raise ValueError(f"unknown table: {table}")
        return self._rows(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]

    def load_lessons(self) -> dict[str, dict]:
        return {r["key"]: r for r in self._rows("SELECT * FROM lessons")}

    def lessons_list(self) -> list[dict]:
        return self._rows("SELECT * FROM lessons ORDER BY samples DESC")

    def recent_trades(self, limit: int = 20) -> list[dict]:
        return self._rows("SELECT * FROM trades ORDER BY id DESC LIMIT %s", (limit,))

    def recent_decisions(self, limit: int = 20) -> list[dict]:
        return self._rows("SELECT * FROM decisions ORDER BY id DESC LIMIT %s", (limit,))

    def metrics_history(self, limit: int = 200) -> list[dict]:
        return self._rows("SELECT * FROM metrics ORDER BY id DESC LIMIT %s", (limit,))[::-1]

    def latest_metric(self) -> dict | None:
        rows = self._rows("SELECT * FROM metrics ORDER BY id DESC LIMIT 1")
        return rows[0] if rows else None
