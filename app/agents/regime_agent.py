"""Regime agent — wraps the regime classifier into a vote.

Bullish regimes nudge the directional score up; bearish down; sideways/high-vol
toward neutral with reduced confidence. The CIO also consumes the raw
RegimeAssessment separately for exposure decisions.
"""

from __future__ import annotations

import pandas as pd

from app.agents.base import AnalyticAgent
from app.core.constants import MarketRegime
from app.models import AgentVote
from app.strategies.regime import classify_regime

_REGIME_SCORE = {
    MarketRegime.BULL: 60.0,
    MarketRegime.RECOVERY: 25.0,
    MarketRegime.SIDEWAYS: 0.0,
    MarketRegime.HIGH_VOL: -15.0,
    MarketRegime.BEAR: -60.0,
    MarketRegime.CRASH: -85.0,
}


class RegimeAgent(AnalyticAgent):
    name = "RegimeAI"
    role = "regime"

    def analyze(self, asset: str, data: dict[str, pd.DataFrame]) -> AgentVote:
        df = data.get("1D")
        if df is None:
            df = next(v for k, v in data.items() if k != "_context")
        assessment = classify_regime(df)
        score = _REGIME_SCORE.get(assessment.regime, 0.0)
        flags = []
        if assessment.regime in (MarketRegime.CRASH, MarketRegime.HIGH_VOL):
            flags.append(f"regime_{assessment.regime.value}")
        return self._vote(
            asset,
            score,
            assessment.confidence,
            f"regime={assessment.regime.value} ({assessment.reasoning})",
            flags,
            {"regime": assessment.regime.value, "regime_confidence": assessment.confidence},
        )
