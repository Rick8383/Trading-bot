"""CIO agent — final decision authority (subordinate only to the Risk veto).

Responsibilities:
  * Blend role scores into conviction (applying any *learned* penalties).
  * Choose direction from the net bias and regime constraints.
  * Build entry/stop/target, estimate win probability, evaluate EV/RR.
  * Emit a TradeIdea for the Risk Manager to ratify, then a FinalDecision.

The CIO can accept, reduce, or refuse — but it can never overrule a hard risk
veto, and it can never size beyond the risk-bounded maximum.
"""

from __future__ import annotations

import numpy as np

from app.core.config import Settings
from app.core.constants import Action, MarketRegime
from app.decision import conviction as conv
from app.decision.adaptive_risk import RiskParams
from app.decision.expected_value import evaluate
from app.models import FinalDecision, RegimeAssessment, TradeIdea
from app.risk.position_sizing import calculate_position_size, position_weight
from app.risk.stop_manager import atr_stop, take_profit
from app.scoring.vote_engine import AggregatedVotes


class CIOAgent:
    name = "CIO_AI"

    def __init__(self, settings: Settings):
        self.s = settings

    def form_idea(
        self,
        *,
        asset: str,
        agg: AggregatedVotes,
        regime: RegimeAssessment,
        last_price: float,
        atr: float,
        risk_params: RiskParams,
        learned_penalties: dict[str, float] | None = None,
    ) -> TradeIdea | None:
        learned_penalties = learned_penalties or {}

        # 1) Conviction from role scores, weighted per config.
        weights = {
            "trend": self.s.cio_weights.trend,
            "momentum": self.s.cio_weights.momentum,
            "regime": self.s.cio_weights.regime,
            "quant": self.s.cio_weights.quant,
            "macro": self.s.cio_weights.macro,
            "volume": self.s.cio_weights.other,
            "pattern": self.s.cio_weights.other * 0.5,   # SMC: low weight (noisy)
            "ml": self.s.cio_weights.other * 0.5,        # ML: advisory only
        }
        base_conviction = conv.compute_conviction(agg.role_scores, weights)

        # 2) Apply learned penalties (capped) — the self-improvement feedback.
        penalty = min(sum(learned_penalties.values()), self.s.learning.max_conviction_penalty)
        conviction = max(0.0, base_conviction - penalty)

        # 3) Direction from net bias, constrained by regime.
        if agg.directional_bias > 8:
            action = Action.LONG
        elif agg.directional_bias < -8:
            action = Action.SHORT
        else:
            return None  # no clear edge -> FLAT (handled by caller)

        if action == Action.SHORT and not risk_params.shorts_allowed:
            return None
        if regime.regime == MarketRegime.CRASH:
            return None  # stand aside in a crash

        # 4) Below the trade floor -> no position.
        if conviction < self.s.conviction.flat_below:
            return None

        # 5) Build levels from ATR. Missing/zero ATR -> cannot define risk.
        if atr <= 0 or last_price <= 0:
            return None
        stop = atr_stop(last_price, atr, action, self.s.strategy.atr_stop_multiplier)
        target = take_profit(last_price, stop, action, max(self.s.risk.min_rr, 2.0))

        # 6) Win probability from conviction (deliberately conservative band).
        win_prob = float(np.clip(0.40 + conviction / 100 * 0.25, 0.40, 0.68))
        ev = evaluate(
            win_prob=win_prob, entry=last_price, stop=stop, target=target, min_rr=self.s.risk.min_rr
        )
        if not ev.accept:
            return None

        idea = TradeIdea(
            asset=asset,
            action=action,
            conviction=conviction,
            entry=last_price,
            stop_loss=stop,
            take_profit=target,
            expected_value=ev.expected_value,
            reward_risk=ev.reward_risk,
            win_probability=win_prob,
            votes=agg.per_agent,
        )
        return idea

    def finalize(
        self,
        idea: TradeIdea,
        *,
        regime: RegimeAssessment,
        risk_params: RiskParams,
        approved: bool,
        rejection_reason: str | None,
        learned_penalties: dict[str, float],
    ) -> FinalDecision:
        consulted = sorted({v.agent for v in idea.votes}) + [self.name, "RiskManager_AI"]
        if not approved:
            return FinalDecision(
                asset=idea.asset, action=Action.FLAT, conviction=idea.conviction,
                rejected=True, rejection_reason=rejection_reason, regime=regime.regime,
                consulted_agents=consulted, risk_flags=[v for vt in idea.votes for v in vt.risk_flags],
                learned_penalties=learned_penalties,
            )

        alloc = conv.allocation_factor(idea.conviction, self.s.conviction)
        size = calculate_position_size(
            capital=self.s.capital.initial,
            risk_pct=risk_params.risk_per_trade,
            entry_price=idea.entry,
            stop_price=idea.stop_loss,
            allocation_factor=alloc,
            max_asset_weight=self.s.risk.max_asset_exposure,
        )
        weight = position_weight(size, idea.entry, self.s.capital.initial)
        return FinalDecision(
            asset=idea.asset,
            action=idea.action,
            conviction=idea.conviction,
            allocation=weight,
            quantity=size,
            entry=idea.entry,
            stop_loss=idea.stop_loss,
            take_profit=idea.take_profit,
            expected_value=idea.expected_value,
            reward_risk=idea.reward_risk,
            rejected=False,
            regime=regime.regime,
            consulted_agents=consulted,
            risk_flags=sorted({f for vt in idea.votes for f in vt.risk_flags}),
            learned_penalties=learned_penalties,
        )
