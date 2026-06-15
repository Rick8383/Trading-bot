"""Market-structure agent — swing-based HH/HL/LH/LL classification.

A lightweight, fully deterministic structure read: detect swing highs/lows via a
rolling fractal, then classify the recent sequence as uptrend / downtrend /
range. Heavier SMC concepts (BOS/CHOCH, FVG, liquidity sweeps, Wyckoff) are
Phase 2 — and per spec they stay *low-weighted* because they're hard to detect
reliably.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.agents.base import AnalyticAgent
from app.models import AgentVote


def _swings(series: pd.Series, window: int = 5) -> tuple[list[float], list[float]]:
    highs, lows = [], []
    arr = series.values
    for i in range(window, len(arr) - window):
        seg = arr[i - window : i + window + 1]
        if arr[i] == seg.max():
            highs.append(arr[i])
        if arr[i] == seg.min():
            lows.append(arr[i])
    return highs[-3:], lows[-3:]


class MarketStructureAgent(AnalyticAgent):
    name = "MarketStructureAI"
    role = "pattern"

    def analyze(self, asset: str, data: dict[str, pd.DataFrame]) -> AgentVote:
        df = data.get("1D")
        if df is None:
            df = next(v for k, v in data.items() if k != "_context")
        if len(df) < 40:
            return self._vote(asset, 0.0, 0.2, "insufficient data")

        highs, lows = _swings(df["high"], window=5)
        score = 0.0
        label = "range"
        if len(highs) >= 2 and len(lows) >= 2:
            hh = highs[-1] > highs[-2]
            hl = lows[-1] > lows[-2]
            lh = highs[-1] < highs[-2]
            ll = lows[-1] < lows[-2]
            if hh and hl:
                score, label = 50.0, "uptrend (HH/HL)"
            elif lh and ll:
                score, label = -50.0, "downtrend (LH/LL)"
            else:
                score, label = 0.0, "range/transition"
        return self._vote(asset, score, 0.45, f"structure={label}", [], {"structure": label})
