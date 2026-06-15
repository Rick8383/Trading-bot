"""Real-time decision loop.

On each tick: pull the latest candles, run the decision pipeline, execute
approved decisions through the configured broker (paper by default), persist
everything, and — for the in-process paper broker — mark-to-market and learn
from any closed trades. Uses APScheduler when available; otherwise a simple
threaded interval loop. ``run_once`` is synchronous and unit-tested with mocks.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from app.agents import DEFAULT_ANALYTIC_AGENTS
from app.agents.audit_agent import AuditAgent
from app.agents.cio_agent import CIOAgent
from app.core.config import Settings
from app.core.constants import Action
from app.core.logging import get_logger
from app.data import indicators as ind
from app.data.market_data import MarketDataProvider
from app.data.providers import resample_ohlcv
from app.decision.exposure import Position
from app.execution.order_validator import Order
from app.execution.paper_broker import PaperBroker
from app.learning.knowledge_base import KnowledgeBase
from app.learning.postmortem import post_mortem
from app.learning.trade_journal import TradeJournal, TradeRecord
from app.orchestration.pipeline import DecisionPipeline, PortfolioState
from app.risk.drawdown_guard import DrawdownGuard
from app.risk.risk_manager import RiskManager

_log = get_logger("loop")


@dataclass
class RealtimeRunner:
    settings: Settings
    provider: MarketDataProvider
    broker: object                      # PaperBroker or a live adapter
    symbols: list[str]
    store: object | None = None
    ema_periods: tuple[int, ...] = field(default=(20, 50, 100, 200))

    def __post_init__(self) -> None:
        self.kb = KnowledgeBase(self.settings.learning.store_path, self.settings.learning.min_samples_for_lesson)
        self.journal = TradeJournal(self.settings.learning.journal_path)
        self.audit = AuditAgent()
        self.guard = DrawdownGuard(self.settings.capital.initial, self.settings.capital.initial)
        self.pipeline = DecisionPipeline(
            settings=self.settings, agents=DEFAULT_ANALYTIC_AGENTS,
            risk_manager=RiskManager(self.settings.risk), cio=CIOAgent(self.settings),
            knowledge_base=self.kb, audit=self.audit,
        )
        self._open_context: dict = {}
        self._consecutive_losses = 0

    # --- one cycle -----------------------------------------------------
    def _frames(self) -> dict[str, dict[str, pd.DataFrame]]:
        out: dict[str, dict[str, pd.DataFrame]] = {}
        for sym in self.symbols:
            try:
                df = self.provider.get_ohlcv(sym, "1D", 500)
            except Exception:  # noqa: BLE001
                continue
            if len(df) < 60:
                continue
            tf = {"1D": ind.enrich(df, self.ema_periods)}
            weekly = resample_ohlcv(df, "1W")
            if len(weekly) >= 40:
                tf["1W"] = ind.enrich(weekly, self.ema_periods)
            out[sym] = tf
        return out

    def _portfolio_state(self, marks: dict[str, float]) -> PortfolioState:
        positions: list[Position] = []
        if isinstance(self.broker, PaperBroker):
            equity = self.broker.equity(marks)
            self.guard.update(equity)
            for p in self.broker.positions.values():
                price = marks.get(p.symbol, p.entry)
                w = (p.quantity * price) / equity if equity > 0 else 0.0
                positions.append(Position(p.symbol, p.action, w if p.action == Action.LONG else -w))
        return PortfolioState(positions=positions, drawdown=self.guard.drawdown,
                              daily_loss=self.guard.daily_loss, consecutive_losses=self._consecutive_losses)

    def run_once(self) -> list:
        frames = self._frames()
        if not frames:
            return []
        marks = {s: float(tf["1D"]["close"].iloc[-1]) for s, tf in frames.items()}
        state = self._portfolio_state(marks)

        decisions = self.pipeline.run_cycle(frames, state)
        if self.store:
            for d in decisions:
                self.store.save_decision(d)

        for d in decisions:
            if d.rejected or d.action == Action.FLAT or d.quantity <= 0:
                continue
            if isinstance(self.broker, PaperBroker) and d.asset in self.broker.positions:
                continue
            order = Order(symbol=d.asset, action=d.action, quantity=d.quantity,
                          entry=d.entry, stop_loss=d.stop_loss, take_profit=d.take_profit, leverage=1.0)
            try:
                self.broker.submit(order, decision_ref=d.asset)
                self._open_context[d.asset] = d
            except Exception as exc:  # noqa: BLE001
                _log.warning("submit_failed", symbol=d.asset, error=str(exc)[:120]) if hasattr(_log, "warning") else None

        # Paper broker: settle stops/targets and learn from closes.
        if isinstance(self.broker, PaperBroker):
            for trade in self.broker.mark_to_market(marks):
                self._learn(trade)
        return decisions

    def _learn(self, trade) -> None:
        if trade is None:
            return
        ctx = self._open_context.pop(trade.symbol, None)
        rec = TradeRecord(
            symbol=trade.symbol, action=trade.action.value, entry=trade.entry, exit=trade.exit,
            stop_loss=ctx.stop_loss if ctx else trade.entry, take_profit=ctx.take_profit if ctx else None,
            quantity=trade.quantity, pnl=trade.pnl, return_pct=trade.return_pct, reason=trade.reason,
            conviction=ctx.conviction if ctx else 0.0, reward_risk=ctx.reward_risk if ctx else 0.0,
            regime=ctx.regime.value if (ctx and ctx.regime) else "unknown",
            risk_flags=ctx.risk_flags if ctx else [],
        )
        tags = post_mortem(rec)
        rec.error_tags = [t.key for t in tags]
        self.journal.append(rec)
        self.kb.ingest(rec, tags)
        self.kb.save()
        if self.store:
            self.store.save_trade(rec)
        self._consecutive_losses = self._consecutive_losses + 1 if trade.pnl < 0 else 0

    # --- scheduling ----------------------------------------------------
    def start(self, interval_seconds: int = 3600) -> None:  # pragma: no cover - runtime loop
        """Run the loop forever on an interval. Ctrl-C to stop."""
        try:
            from apscheduler.schedulers.blocking import BlockingScheduler

            sched = BlockingScheduler()
            sched.add_job(self.run_once, "interval", seconds=interval_seconds, next_run_time=None)
            _log.info("scheduler_start", interval=interval_seconds) if hasattr(_log, "info") else None
            self.run_once()
            sched.start()
        except ImportError:
            import time

            while True:
                self.run_once()
                time.sleep(interval_seconds)
