"""Opportunity ranking + cross-sectional relative strength.

The engine prefers a handful of high-conviction names over many mediocre ones.
This module ranks candidate ideas and computes relative strength across the
universe (used by the quant agent).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.models import TradeIdea


def relative_strength(returns: dict[str, float]) -> dict[str, float]:
    """Map each asset's lookback return to a cross-sectional z-score in [-100,100]."""
    if not returns:
        return {}
    vals = np.array(list(returns.values()), dtype=float)
    mean, std = np.nanmean(vals), np.nanstd(vals)
    if std == 0 or np.isnan(std):
        return {k: 0.0 for k in returns}
    return {k: float(np.clip((v - mean) / std * 40, -100, 100)) for k, v in returns.items()}


def lookback_returns(frames: dict[str, pd.DataFrame], period: int = 63) -> dict[str, float]:
    out = {}
    for sym, df in frames.items():
        if len(df) > period:
            out[sym] = float(df["close"].pct_change(period).iloc[-1])
    return out


def rank_opportunities(ideas: list[TradeIdea], top_n: int | None = None) -> list[TradeIdea]:
    """Sort by an EV-aware conviction score, best first."""
    def key(i: TradeIdea) -> float:
        # Conviction is primary; EV and RR break ties and reward asymmetry.
        return i.conviction + 5 * max(0.0, i.expected_value) + 2 * i.reward_risk

    ranked = sorted(ideas, key=key, reverse=True)
    return ranked[:top_n] if top_n else ranked
