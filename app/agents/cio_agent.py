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
from app.risk.stop_manager import atr_stop, structure_stop, structure_target, take_profit
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
        learned_bonuses: dict[str, float] | None = None,
        df=None,
    ) -> TradeIdea | None:
        learned_penalties = learned_penalties or {}
        learned_bonuses = learned_bonuses or {}

        weights = {
            "trend": self.s.cio_weights.trend,
            "momentum": self.s.cio_weights.momentum,
            "regime": self.s.cio_weights.regime,
            "quant": self.s.cio_weights.quant,
            "macro": self.s.cio_weights.macro,
            "volume": self.s.cio_weights.other,
            "pattern": self.s.cio_weights.other * 0.5,   # SMC: low weight (noisy)
            "ml": self.s.cio_weights.other * 0.5,        # ML: advisory only
            "news": self.s.cio_weights.other * 0.5,      # headline sentiment
            "sentiment": self.s.cio_weights.other * 0.5,  # social: contrarian damping
        }

        # 1) Direction FIRST, from the net bias (long, short, or flat).
        bt = self.s.conviction.bias_threshold
        if agg.directional_bias > bt:
            action, sign = Action.LONG, 1.0
        elif agg.directional_bias < -bt:
            action, sign = Action.SHORT, -1.0
        else:
            return None  # no clear edge -> FLAT (handled by caller)

        if action == Action.SHORT and not risk_params.shorts_allowed:
            return None
        if regime.regime == MarketRegime.CRASH:
            return None  # stand aside in a crash

        # 2) Conviction = strength of agreement *in the chosen direction*. Orient
        #    role scores by the trade side so a strong bearish read yields HIGH
        #    short conviction (previously signed blending clamped shorts to ~0,
        #    so the bot almost never shorted and under-counted mixed longs).
        oriented = {k: v * sign for k, v in agg.role_scores.items()}
        base_conviction = conv.compute_conviction(oriented, weights)

        # 3) Apply learned penalties AND bonuses (both capped).
        cap = self.s.learning.max_conviction_penalty
        penalty = min(sum(learned_penalties.values()), cap)
        bonus = min(sum(learned_bonuses.values()), cap)
        conviction = float(max(0.0, min(100.0, base_conviction - penalty + bonus)))

        # 4) Below the trade floor -> no position.
        if conviction < self.s.conviction.flat_below:
            return None

        # 5) Build levels. Missing/zero ATR -> cannot define risk.
        if atr <= 0 or last_price <= 0:
            return None
        mult = self.s.strategy.atr_stop_multiplier
        min_rr = max(self.s.risk.min_rr, 2.0)

        # 5a) Entry timing: market, or a pullback limit when price is extended.
        entry_price, pending = self._entry_price(df, last_price, atr, action)

        if self.s.strategy.structure_stops and df is not None and len(df) >= 40:
            # Stop just beyond the nearest support/resistance (ATR-bounded);
            # target at the next opposing level when it clears min RR.
            stop = structure_stop(df, entry_price, atr, action, mult)
            target = structure_target(df, entry_price, stop, action, min_rr)
        else:
            stop = atr_stop(entry_price, atr, action, mult)
            target = take_profit(entry_price, stop, action, min_rr)

        # 6) Win probability: a conviction prior, refined by the ML's *calibrated*
        #    probability when the ML agent is present and confident. A data-driven
        #    win_prob feeds straight into the EV gate -> a sharper filter.
        win_prob = float(np.clip(0.40 + conviction / 100 * 0.25, 0.40, 0.68))
        ml_p = self._ml_win_prob(agg, action)
        if ml_p is not None:
            w = self.s.strategy.ml_win_prob_weight
            win_prob = float(np.clip((1 - w) * win_prob + w * ml_p, 0.30, 0.75))
        ev = evaluate(
            win_prob=win_prob, entry=entry_price, stop=stop, target=target, min_rr=self.s.risk.min_rr
        )
        if not ev.accept:
            return None

        # 6b) Edge net of costs: a trade must clear the round-trip cost (entry +
        #     exit slippage & commission) by a buffer. This is the anti-overtrading
        #     gate that matters most intraday, where costs eat small moves.
        ex = self.s.execution
        round_trip_cost_pct = 2 * (ex.slippage_bps + ex.commission_bps) / 10_000 * 100
        net_ev = ev.expected_value - round_trip_cost_pct
        if ex.cost_aware and net_ev < ex.min_edge_pct:
            return None
        net_ev = net_ev if ex.cost_aware else ev.expected_value

        idea = TradeIdea(
            asset=asset,
            action=action,
            conviction=conviction,
            entry=entry_price,
            stop_loss=stop,
            take_profit=target,
            expected_value=net_ev,          # net of round-trip costs (honest)
            reward_risk=ev.reward_risk,
            win_probability=win_prob,
            pending=pending,
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
        learned_bonuses: dict[str, float] | None = None,
        portfolio_scale: float = 1.0,
    ) -> FinalDecision:
        learned_bonuses = learned_bonuses or {}
        consulted = sorted({v.agent for v in idea.votes}) + [self.name, "RiskManager_AI"]
        if not approved:
            return FinalDecision(
                asset=idea.asset, action=Action.FLAT, conviction=idea.conviction,
                rejected=True, rejection_reason=rejection_reason, regime=regime.regime,
                consulted_agents=consulted, risk_flags=[v for vt in idea.votes for v in vt.risk_flags],
                learned_penalties=learned_penalties, learned_bonuses=learned_bonuses,
            )

        # Shrink size by the correlation scale (1.0 = uncorrelated, < 1 = crowded).
        alloc = conv.allocation_factor(idea.conviction, self.s.conviction) * max(0.0, min(1.0, portfolio_scale))
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
            pending=idea.pending,
            rejected=False,
            regime=regime.regime,
            consulted_agents=consulted,
            risk_flags=sorted({f for vt in idea.votes for f in vt.risk_flags}),
            learned_penalties=learned_penalties, learned_bonuses=learned_bonuses,
        )

    def _ml_win_prob(self, agg: AggregatedVotes, action: Action) -> float | None:
        """Extract the ML agent's calibrated P(up), oriented to the trade side.

        Returns None when no confident ML vote is present, so non-ML rosters are
        unaffected. For shorts we use 1 - P(up).
        """
        for v in agg.per_agent:
            if v.features.get("role") == "ml" and "p_up" in v.features and v.confidence >= 0.3:
                p_up = float(v.features["p_up"])
                return p_up if action == Action.LONG else 1.0 - p_up
        return None

    def _entry_price(self, df, last_price: float, atr: float, action: Action) -> tuple[float, bool]:
        """Market entry, or a pullback limit when price is extended from EMA20.

        Returns (entry_price, pending). A pullback limit improves reward/risk by
        entering nearer the zone, but only when price is meaningfully extended;
        otherwise we enter at market to avoid missing the move.
        """
        cfg = self.s.entries
        if (not cfg.enabled) or cfg.mode != "pullback" or df is None or "ema20" not in df:
            return last_price, False
        import pandas as pd

        ema20 = df["ema20"].iloc[-1]
        if pd.isna(ema20):
            return last_price, False

        if action == Action.LONG:
            extended = last_price > ema20 + cfg.max_extension_atr * atr
            limit = ema20 + cfg.pullback_buffer_atr * atr
            if extended and limit < last_price:
                return float(limit), True
        elif action == Action.SHORT:
            extended = last_price < ema20 - cfg.max_extension_atr * atr
            limit = ema20 - cfg.pullback_buffer_atr * atr
            if extended and limit > last_price:
                return float(limit), True
        return last_price, False
