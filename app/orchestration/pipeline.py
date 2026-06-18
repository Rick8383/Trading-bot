"""Decision pipeline — the canonical 10-step flow, risk-first and auditable.

    1. data            5. adaptive risk        9. CIO finalize
    2. relative str.   6. capital preservation 10. audit
    3. agents          7. learned penalties
    4. aggregate+regime 8. risk veto

Given a snapshot of multi-timeframe frames per symbol plus portfolio/risk state,
it returns one FinalDecision per symbol. It never executes — execution is a
separate, explicitly-invoked step.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.agents.base import AnalyticAgent
from app.agents.cio_agent import CIOAgent
from app.core.config import Settings
from app.core.constants import Action
from app.decision.adaptive_risk import adapt_risk
from app.decision.capital_preservation import evaluate_drawdown
from app.decision.exposure import Position
from app.decision.portfolio import assess_candidate, correlation_matrix
from app.learning.knowledge_base import KnowledgeBase
from app.learning.postmortem import setup_signature
from app.models import FinalDecision
from app.risk.risk_manager import RiskManager
from app.scoring.ranking import lookback_returns, relative_strength
from app.scoring.vote_engine import aggregate
from app.strategies.regime import classify_regime


@dataclass
class PortfolioState:
    positions: list[Position]
    drawdown: float = 0.0
    daily_loss: float = 0.0
    consecutive_losses: int = 0


class DecisionPipeline:
    def __init__(
        self,
        settings: Settings,
        agents: list[AnalyticAgent],
        risk_manager: RiskManager,
        cio: CIOAgent,
        knowledge_base: KnowledgeBase | None = None,
        audit=None,
        news_provider=None,
        sentiment_provider=None,
    ):
        self.s = settings
        self.agents = agents
        self.risk = risk_manager
        self.cio = cio
        self.kb = knowledge_base
        self.audit = audit
        self.news_provider = news_provider
        self.sentiment_provider = sentiment_provider

    @staticmethod
    def _macro_breadth(daily: dict[str, pd.DataFrame]) -> tuple[float, float | None]:
        """Risk-On/Off proxy from market breadth: fraction of names > EMA50.

        Returns (macro_score in [-100,100], breadth fraction) or (0, None) if the
        universe is too small to be meaningful (single-asset runs).
        """
        ups, total = 0, 0
        for df in daily.values():
            if len(df) < 50 or "ema50" not in df:
                continue
            last = df.iloc[-1]
            if pd.isna(last.get("ema50")):
                continue
            total += 1
            if last["close"] > last["ema50"]:
                ups += 1
        if total < 3:
            return 0.0, None
        breadth = ups / total
        return float((breadth - 0.5) * 200), breadth   # 0%->-100, 100%->+100

    @staticmethod
    def _collect(provider, symbols) -> dict[str, float]:
        if provider is None:
            return {}
        out: dict[str, float] = {}
        for sym in symbols:
            try:
                score, _, _ = provider.score(sym)
                out[sym] = score
            except Exception:  # noqa: BLE001
                continue
        return out

    def run_cycle(
        self,
        frames: dict[str, dict[str, pd.DataFrame]],
        state: PortfolioState,
    ) -> list[FinalDecision]:
        # Step 2: cross-sectional relative strength (needs the whole universe).
        daily = {sym: tf["1D"] for sym, tf in frames.items() if "1D" in tf}
        rs = relative_strength(lookback_returns(daily))
        macro_score, breadth = self._macro_breadth(daily)

        # Portfolio layer: correlation matrix + currently-held names.
        corr = correlation_matrix(daily, self.s.portfolio.corr_lookback)
        held = [p.asset for p in state.positions]

        # Optional external feeds (news/social). Default: no feed -> neutral.
        news = self._collect(self.news_provider, daily.keys())
        sentiment = self._collect(self.sentiment_provider, daily.keys())

        decisions: list[FinalDecision] = []
        for symbol, tf_frames in frames.items():
            ctx = {
                "relative_strength": rs.get(symbol, 0.0),
                "macro_score": macro_score,
                "breadth": breadth,
                "news": news,
                "sentiment": sentiment,
            }
            data = {**tf_frames, "_context": ctx}

            # Step 3: analytic agents -> votes.
            votes = [a.analyze(symbol, data) for a in self.agents]
            # Step 4: aggregate + regime.
            agg = aggregate(votes)
            df1d = tf_frames.get("1D")
            if df1d is None or len(df1d) < 60:
                continue
            regime = classify_regime(df1d)

            last = df1d.iloc[-1]
            last_price = float(last["close"])
            atr = float(last.get("atr", np.nan))
            rvol = float(last.get("rvol", np.nan)) if not pd.isna(last.get("rvol", np.nan)) else None

            # Step 5: adaptive risk parameters.
            rp = adapt_risk(
                base_risk=self.s.risk.risk_per_trade,
                regime=regime.regime,
                realized_vol=rvol,
                consecutive_losses=state.consecutive_losses,
            )
            # Step 6: capital preservation -> exposure cap / kill conditions.
            pres = evaluate_drawdown(state.drawdown, self.s.drawdown_ladder, self.s.risk.max_drawdown)
            exposure_cap = min(rp.gross_exposure_cap, pres.max_exposure)

            # Step 7: learned penalties for this prospective setup.
            prospective_action = Action.LONG if agg.directional_bias >= 0 else Action.SHORT
            sig = setup_signature(
                action=prospective_action.value, regime=regime.regime.value,
                conviction=60, reward_risk=2.0, risk_flags=agg.risk_flags,
            )
            penalties = self.kb.penalties(sig) if self.kb else {}
            bonuses = self.kb.bonuses(sig) if self.kb else {}

            # Step 8/9: CIO forms an idea, risk vetoes, CIO finalizes.
            idea = self.cio.form_idea(
                asset=symbol, agg=agg, regime=regime, last_price=last_price,
                atr=atr if not pd.isna(atr) else 0.0, risk_params=rp, learned_penalties=penalties,
                learned_bonuses=bonuses, df=df1d,
            )
            if idea is None:
                decision = FinalDecision(
                    asset=symbol, action=Action.FLAT, conviction=0.0, rejected=True,
                    rejection_reason="no statistical edge (EV<=0 / low conviction / regime)",
                    regime=regime.regime, consulted_agents=[a.name for a in self.agents],
                    risk_flags=agg.risk_flags, learned_penalties=penalties,
                    learned_bonuses=bonuses,
                )
            else:
                # Portfolio: veto if too correlated with the book, else shrink size.
                corr_block, corr_scale, corr_reason = assess_candidate(
                    symbol, [h for h in held if h != symbol], corr, self.s.portfolio
                )
                verdict = self.risk.validate(
                    idea, portfolio=state.positions, preservation=pres,
                    daily_loss=state.daily_loss, shorts_allowed=rp.shorts_allowed,
                    exposure_cap=exposure_cap, correlation_block=corr_block,
                    correlation_reason=corr_reason,
                )
                decision = self.cio.finalize(
                    idea, regime=regime, risk_params=rp, approved=verdict.approved,
                    rejection_reason=None if verdict.approved else verdict.reason,
                    learned_penalties=penalties, learned_bonuses=bonuses, portfolio_scale=corr_scale,
                )

            if self.audit:
                self.audit.record_decision(decision)
            decisions.append(decision)

        return decisions
