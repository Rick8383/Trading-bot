"""Trend agent — EMA stack alignment + multi-timeframe confirmation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.agents.base import AnalyticAgent
from app.core.constants import TIMEFRAME_WEIGHTS
from app.models import AgentVote


def _tf_trend_score(df: pd.DataFrame) -> float:
    """Single-timeframe trend score in [-100, 100] from the EMA stack.

    Degrades gracefully on shorter histories (e.g. a weekly series with <200
    bars): it scores only the EMA rungs that are actually available, and uses
    the longest available EMA as the anchor for the distance term.
    """
    if len(df) < 40:
        return 0.0
    last = df.iloc[-1]
    price = last["close"]
    emas = [last.get(f"ema{p}") for p in (20, 50, 100, 200)]
    present = [(p, e) for p, e in zip((20, 50, 100, 200), emas) if not pd.isna(e)]
    if len(present) < 2:
        return 0.0

    # Score each adjacent rung (price>ema, then each faster EMA above slower).
    levels = [price] + [e for _, e in present]
    rungs = [levels[i] > levels[i + 1] for i in range(len(levels) - 1)]
    bull = sum(rungs)
    bear = sum(not r for r in rungs)
    score = (bull - bear) / len(rungs) * 100

    anchor = present[-1][1]  # longest available EMA
    dist = (price / anchor - 1) * 100
    score += float(np.clip(dist, -25, 25))
    return float(np.clip(score, -100, 100))


class TrendAgent(AnalyticAgent):
    name = "TrendAI"
    role = "trend"

    def analyze(self, asset: str, data: dict[str, pd.DataFrame]) -> AgentVote:
        scores: dict[str, float] = {}
        for tf, df in data.items():
            scores[tf] = _tf_trend_score(df)

        # Weighted multi-timeframe blend (longer timeframes dominate).
        num = sum(scores[tf] * TIMEFRAME_WEIGHTS.get(tf, 0.0) for tf in scores)
        den = sum(TIMEFRAME_WEIGHTS.get(tf, 0.0) for tf in scores) or 1.0
        blended = num / den

        # Confidence: agreement across timeframes (low dispersion -> high conf).
        vals = list(scores.values())
        agreement = 1.0 - (np.std(vals) / 100 if len(vals) > 1 else 0.3)
        same_sign = all(v >= 0 for v in vals) or all(v <= 0 for v in vals)
        confidence = float(np.clip(agreement * (1.0 if same_sign else 0.6), 0.2, 0.95))

        reasoning = f"MTF trend blend={blended:.0f} ({ {k: round(v) for k,v in scores.items()} })"
        flags = [] if same_sign else ["mtf_trend_conflict"]
        return self._vote(asset, blended, confidence, reasoning, flags, {"tf_scores": scores})
