"""Quant agent — composite factor score.

Builds a small factor model (momentum, trend, mean-reversion, volatility) and
blends it into one directional score. Relative-strength is computed by the
pipeline (needs the cross-section) and can be injected via ``data['_context']``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.agents.base import AnalyticAgent
from app.models import AgentVote


class QuantAgent(AnalyticAgent):
    name = "QuantAI"
    role = "quant"

    def analyze(self, asset: str, data: dict[str, pd.DataFrame]) -> AgentVote:
        df = data.get("1D")
        if df is None:
            df = next(v for k, v in data.items() if k != "_context")
        if len(df) < 130:
            return self._vote(asset, 0.0, 0.2, "insufficient data")
        close = df["close"]

        # Momentum factor: blended 1/3/6-month returns (~21/63/126 bars).
        r1 = close.pct_change(21).iloc[-1]
        r3 = close.pct_change(63).iloc[-1]
        r6 = close.pct_change(126).iloc[-1]
        mom = np.nansum([0.2 * r1, 0.3 * r3, 0.5 * r6]) * 100
        mom_score = float(np.clip(mom * 2, -100, 100))

        # Trend factor: price vs EMA100.
        e100 = df.get("ema100")
        trend_score = 0.0
        if e100 is not None and not pd.isna(e100.iloc[-1]):
            trend_score = float(np.clip((close.iloc[-1] / e100.iloc[-1] - 1) * 300, -100, 100))

        # Mean-reversion factor: z-score of price vs 20d mean (contrarian).
        ma20 = close.rolling(20).mean()
        sd20 = close.rolling(20).std()
        z = (close.iloc[-1] - ma20.iloc[-1]) / (sd20.iloc[-1] + 1e-9)
        mr_score = float(np.clip(-z * 20, -40, 40))  # stretched up -> mild fade

        ctx = data.get("_context")
        rs_score = 0.0
        if isinstance(ctx, dict):
            rs_score = float(np.clip(ctx.get("relative_strength", 0.0), -100, 100))

        score = 0.35 * mom_score + 0.30 * trend_score + 0.15 * mr_score + 0.20 * rs_score
        reasoning = f"mom={mom_score:.0f} trend={trend_score:.0f} mr={mr_score:.0f} rs={rs_score:.0f}"
        return self._vote(asset, float(np.clip(score, -100, 100)), 0.55, reasoning, [],
                          {"momentum": mom_score, "rs": rs_score})
