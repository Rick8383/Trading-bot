"""Macro agent — Risk-On / Risk-Off from market breadth (+ optional feed).

Default signal is **market breadth**, injected by the pipeline: the fraction of
the universe in an uptrend. Broad participation -> Risk-On (mild bullish tilt);
deteriorating breadth -> Risk-Off. A real macro feed (rates, inflation,
liquidity) can override via context["macro_score"].
"""

from __future__ import annotations

import pandas as pd

from app.agents.base import AnalyticAgent
from app.models import AgentVote


class MacroAgent(AnalyticAgent):
    name = "MacroAI"
    role = "macro"

    def analyze(self, asset: str, data: dict[str, pd.DataFrame]) -> AgentVote:
        ctx = data.get("_context") or {}
        macro = ctx.get("macro_score")
        if macro is None:
            return self._vote(asset, 0.0, 0.2, "macro: no breadth/feed (neutral)")
        breadth = ctx.get("breadth")
        label = "Risk-On" if macro > 10 else ("Risk-Off" if macro < -10 else "Neutral")
        reason = f"macro={label} ({macro:+.0f}" + (f", breadth={breadth:.0%}" if breadth is not None else "") + ")"
        flags = ["risk_off"] if macro < -25 else []
        return self._vote(asset, float(macro), 0.45, reason, flags, {"macro_score": macro})
