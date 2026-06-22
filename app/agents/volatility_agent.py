"""Volatility agent — assesses risk environment & sizing posture.

Unlike directional agents, this one mostly informs *how much* to risk, not
which way. Its score is mildly negative when volatility is extreme (favor
caution / smaller size), neutral otherwise. It always emits useful features
(atr_pct, realized vol) for the sizing layer.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.agents.base import AnalyticAgent
from app.models import AgentVote


class VolatilityAgent(AnalyticAgent):
    name = "VolatilityAI"
    role = "volatility"

    def analyze(self, asset: str, data: dict[str, pd.DataFrame]) -> AgentVote:
        df = data.get("1D")
        if df is None:
            df = next(v for k, v in data.items() if k != "_context")
        if len(df) < 30:
            return self._vote(asset, 0.0, 0.2, "insufficient data")
        last = df.iloc[-1]
        atr = last.get("atr", np.nan)
        price = last["close"]
        rvol = last.get("rvol", np.nan)

        atr_pct = float(atr / price) if not pd.isna(atr) and price > 0 else None
        rvol_series = df["rvol"].dropna()
        vol_pct = float((rvol_series < rvol).mean()) if (not pd.isna(rvol) and len(rvol_series) > 10) else 0.5

        # High vol -> mild negative score (defensive), and a risk flag.
        score = 0.0
        flags: list[str] = []
        if vol_pct > 0.9:
            score = -40.0
            flags.append("extreme_volatility")
        elif vol_pct > 0.75:
            score = -15.0
            flags.append("elevated_volatility")

        confidence = 0.6
        reasoning = f"ATR%={atr_pct:.3f} vol_percentile={vol_pct:.0%}" if atr_pct else f"vol_pct={vol_pct:.0%}"
        return self._vote(asset, score, confidence, reasoning, flags,
                          {"atr_pct": atr_pct, "vol_percentile": vol_pct})
