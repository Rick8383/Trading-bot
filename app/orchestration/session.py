"""Paper-trading session — the founder's test harness on fictional capital.

Wires the whole stack together and walks it forward bar-by-bar over historical
(or synthetic) data:

    decide -> execute (paper) -> mark-to-market -> on close: journal + learn

Every closed trade is journaled, post-mortem'd, and folded into the knowledge
base, so the next cycle is already a little wiser. At the end it reports
performance, the lessons learned, and human-reviewable improvement proposals.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from app.agents import DEFAULT_ANALYTIC_AGENTS
from app.agents.audit_agent import AuditAgent
from app.agents.cio_agent import CIOAgent
from app.core.config import Settings
from app.core.constants import Action
from app.data import indicators as ind
from app.data.market_data import MarketDataProvider, SyntheticConfig, synthetic_ohlcv
from app.data.providers import resample_ohlcv
from app.decision.exposure import Position
from app.execution.order_validator import Order
from app.execution.paper_broker import PaperBroker
from app.learning.improvement_engine import propose_improvements
from app.learning.knowledge_base import KnowledgeBase
from app.learning.postmortem import post_mortem
from app.learning.trade_journal import TradeJournal, TradeRecord
from app.models import FinalDecision
from app.monitoring.kill_switch import KillSwitch, should_trigger
from app.monitoring.metrics import compute_report
from app.orchestration.pipeline import DecisionPipeline, PortfolioState
from app.risk.drawdown_guard import DrawdownGuard
from app.risk.risk_manager import RiskManager


@dataclass
class SessionResult:
    equity_curve: list[float]
    trade_returns: list[float]
    decisions: int
    executed: int
    report: object
    lessons: list
    proposals: list
    kill_switched: bool = False


@dataclass
class PaperTradingSession:
    settings: Settings
    timeframes: tuple[str, ...] = ("1D", "1W")
    history: dict[str, pd.DataFrame] = field(default_factory=dict)
    store: object | None = None              # optional SQLiteStore for durability
    data_sources: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.broker = PaperBroker(
            cash=self.settings.capital.initial,
            slippage_bps=self.settings.execution.slippage_bps,
            commission_bps=self.settings.execution.commission_bps,
            max_leverage=self.settings.risk.default_leverage,
        )
        self.kb = KnowledgeBase(self.settings.learning.store_path, self.settings.learning.min_samples_for_lesson)
        self.journal = TradeJournal(self.settings.learning.journal_path)
        self.audit = AuditAgent()
        self.kill = KillSwitch()
        self.guard = DrawdownGuard(self.settings.capital.initial, self.settings.capital.initial)
        self.pipeline = DecisionPipeline(
            settings=self.settings,
            agents=DEFAULT_ANALYTIC_AGENTS,
            risk_manager=RiskManager(self.settings.risk),
            cio=CIOAgent(self.settings),
            knowledge_base=self.kb,
            audit=self.audit,
        )
        self._consecutive_losses = 0
        self._open_context: dict[str, FinalDecision] = {}

    # --- data ----------------------------------------------------------
    def load_synthetic(self, symbols: list[str], bars: int = 400) -> None:
        for sym in symbols:
            self.history[sym] = synthetic_ohlcv(sym, SyntheticConfig(bars=bars))
            self.data_sources[sym] = "synthetic"

    def load_synthetic_mixed(self, symbols: list[str], bars: int = 400) -> None:
        """Load synthetic data spanning bull/bear/sideways regimes.

        Used for offline demos so the learning loop sees genuinely different
        regimes (and thus surfaces lessons like regime-misalignment losses).
        """
        drifts = [0.004, -0.004, 0.0003, 0.005, -0.003, 0.0]
        vols = [0.012, 0.018, 0.02, 0.013, 0.022, 0.02]
        for i, sym in enumerate(symbols):
            cfg = SyntheticConfig(bars=bars, drift=drifts[i % len(drifts)],
                                  volatility=vols[i % len(vols)], seed=11 + i)
            self.history[sym] = synthetic_ohlcv(sym, cfg)
            self.data_sources[sym] = "synthetic_mixed"

    def load_from_provider(self, provider: MarketDataProvider, symbols: list[str], bars: int = 500) -> None:
        """Fetch daily history per symbol from a real provider (with fallback).

        The simulation is daily-driven; the weekly timeframe is derived by
        resampling, so the multi-timeframe read is genuine (1D + 1W).
        """
        for sym in symbols:
            try:
                df = provider.get_ohlcv(sym, "1D", bars)
            except Exception:  # noqa: BLE001
                df = synthetic_ohlcv(sym, SyntheticConfig(bars=bars))
            if len(df) >= 250:
                self.history[sym] = df
                src = getattr(provider, "last_source", {}).get(sym, "live")
                self.data_sources[sym] = src

    def _frames_at(self, t: int) -> dict[str, dict[str, pd.DataFrame]]:
        """Build enriched multi-timeframe frames using data up to bar t (exclusive).

        1D is native; 1W is resampled from the daily window. Both are enriched
        with the indicator panel. Agents weight the timeframes and renormalize
        over whatever is present.
        """
        out: dict[str, dict[str, pd.DataFrame]] = {}
        ema_periods = tuple(self.settings.strategy.ema_periods)
        for sym, df in self.history.items():
            window = df.iloc[:t]
            if len(window) < 60:
                continue
            daily = ind.enrich(window, ema_periods)
            tf_map = {"1D": daily}
            weekly = resample_ohlcv(window, "1W")
            if len(weekly) >= 40:
                tf_map["1W"] = ind.enrich(weekly, ema_periods)
            out[sym] = tf_map
        return out

    # --- main loop -----------------------------------------------------
    def run(self, warmup: int = 220) -> SessionResult:
        symbols = list(self.history.keys())
        n = min(len(df) for df in self.history.values())
        equity_curve: list[float] = []
        decisions_count = 0
        executed = 0

        for t in range(warmup, n):
            frames = self._frames_at(t)
            if not frames:
                continue

            marks_now = {s: float(self.history[s]["close"].iloc[t - 1]) for s in frames}
            equity = self.broker.equity(marks_now)
            self.guard.update(equity)

            # Kill-switch check before taking any new risk.
            reason = should_trigger(
                drawdown=self.guard.drawdown, daily_loss=self.guard.daily_loss,
                max_dd=self.settings.risk.max_drawdown, daily_limit=self.settings.risk.daily_loss_limit,
            )
            if reason:
                self.kill.trigger(reason)
                self.audit.record_event("kill_switch", reason=reason)

            positions = [
                Position(p.symbol, p.action, self._weight(p, marks_now.get(p.symbol, p.entry), equity))
                for p in self.broker.positions.values()
            ]
            state = PortfolioState(
                positions=positions, drawdown=self.guard.drawdown,
                daily_loss=self.guard.daily_loss, consecutive_losses=self._consecutive_losses,
            )

            decisions = self.pipeline.run_cycle(frames, state)
            decisions_count += len(decisions)
            if self.store:
                for d in decisions:
                    self.store.save_decision(d)

            if not self.kill.is_active:
                executed += self._execute(decisions)

            # Mark-to-market against the new bar; learn from any closes.
            marks_next = {s: float(self.history[s]["close"].iloc[t]) for s in frames}
            self._settle_closes(self.broker.mark_to_market(marks_next))
            equity_curve.append(self.broker.equity(marks_next))

        # Liquidate remaining positions at the last price and learn from them.
        final_marks = {s: float(df["close"].iloc[n - 1]) for s, df in self.history.items()}
        for sym in list(self.broker.positions.keys()):
            self._settle_closes([self.broker.close(sym, final_marks[sym], "session_end")])

        self.kb.save()
        trade_returns = [c.return_pct for c in self.broker.closed]
        report = compute_report(equity_curve or [self.settings.capital.initial], trade_returns)
        proposals = propose_improvements(self.kb, self.journal.load())
        if self.store:
            self.store.upsert_lessons(self.kb.lessons)
            self.store.save_metric(equity_curve[-1] if equity_curve else self.settings.capital.initial,
                                   self.guard.drawdown, report)
        return SessionResult(
            equity_curve=equity_curve, trade_returns=trade_returns, decisions=decisions_count,
            executed=executed, report=report, lessons=self.kb.active_lessons(),
            proposals=proposals, kill_switched=self.kill.is_active,
        )

    # --- helpers -------------------------------------------------------
    def _weight(self, pos, price: float, equity: float) -> float:
        if equity <= 0:
            return 0.0
        signed = pos.quantity * price / equity
        return signed if pos.action == Action.LONG else -signed

    def _execute(self, decisions: list[FinalDecision]) -> int:
        count = 0
        for d in decisions:
            if d.rejected or d.action == Action.FLAT or d.quantity <= 0:
                continue
            if d.asset in self.broker.positions:
                continue  # already hold this name
            order = Order(
                symbol=d.asset, action=d.action, quantity=d.quantity,
                entry=d.entry, stop_loss=d.stop_loss, take_profit=d.take_profit,
                leverage=1.0,
            )
            try:
                self.broker.submit(order, decision_ref=d.asset)
                self._open_context[d.asset] = d
                count += 1
            except (ValueError, Exception):
                continue  # insufficient cash / validation -> skip silently, stay safe
        return count

    def _settle_closes(self, closed_trades) -> None:
        for trade in closed_trades:
            if trade is None:
                continue
            ctx = self._open_context.pop(trade.symbol, None)
            rec = TradeRecord(
                symbol=trade.symbol, action=trade.action.value, entry=trade.entry, exit=trade.exit,
                stop_loss=ctx.stop_loss if ctx else trade.entry, take_profit=ctx.take_profit if ctx else None,
                quantity=trade.quantity, pnl=trade.pnl, return_pct=trade.return_pct, reason=trade.reason,
                conviction=ctx.conviction if ctx else 0.0,
                expected_value=ctx.expected_value if ctx else 0.0,
                reward_risk=ctx.reward_risk if ctx else 0.0,
                regime=ctx.regime.value if (ctx and ctx.regime) else "unknown",
                risk_flags=ctx.risk_flags if ctx else [],
                consulted_agents=ctx.consulted_agents if ctx else [],
            )
            tags = post_mortem(rec)
            rec.error_tags = [t.key for t in tags]
            self.journal.append(rec)
            self.kb.ingest(rec, tags)
            if self.store:
                self.store.save_trade(rec)

            # Track loss streak for adaptive de-risking.
            if trade.pnl < 0:
                self._consecutive_losses += 1
            else:
                self._consecutive_losses = 0
