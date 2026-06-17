"""Structure levels: supports / resistances / liquidity pools / FVG edges.

These are the price levels the market actually respects. We use them to place
stops *beyond* a level (where being wrong is confirmed) and targets *at* the
next opposing level (where price is likely to react) — instead of arbitrary ATR
multiples or a fixed reward/risk.

Pure functions over an OHLCV DataFrame (lowercase columns). Deterministic.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def swing_points(high: pd.Series, low: pd.Series, window: int = 3) -> tuple[list[float], list[float]]:
    """Fractal swing highs (resistances) and swing lows (supports)."""
    h, l = high.values, low.values
    highs, lows = [], []
    for i in range(window, len(h) - window):
        if h[i] == h[i - window:i + window + 1].max():
            highs.append(float(h[i]))
        if l[i] == l[i - window:i + window + 1].min():
            lows.append(float(l[i]))
    return highs, lows


def _fvg_edges(df: pd.DataFrame, lookback: int = 40) -> tuple[list[float], list[float]]:
    """Unfilled Fair Value Gap edges act as support (bullish) / resistance (bearish)."""
    h, l = df["high"].values, df["low"].values
    sup, res = [], []
    start = max(2, len(df) - lookback)
    for i in range(start, len(df)):
        if l[i] > h[i - 2]:           # bullish FVG -> its lower edge is support
            sup.append(float(h[i - 2]))
        if h[i] < l[i - 2]:           # bearish FVG -> its upper edge is resistance
            res.append(float(l[i - 2]))
    return sup, res


def support_resistance(df: pd.DataFrame, window: int = 3, lookback: int = 60) -> tuple[list[float], list[float]]:
    """Collect candidate supports and resistances.

    Sources: swing highs/lows, unfilled FVG edges, recent liquidity pools (range
    extremes) and volume-profile nodes (POC + value-area edges). Volume nodes are
    added to *both* pools and filtered by side by nearest_* — the high-volume
    price is a magnet that acts as support from below and resistance from above.
    """
    from app.strategies.volume_profile import profile_levels

    recent = df.tail(max(lookback, window * 4))
    highs, lows = swing_points(recent["high"], recent["low"], window)
    fvg_sup, fvg_res = _fvg_edges(recent, lookback)
    liq_hi = float(recent["high"].max())
    liq_lo = float(recent["low"].min())
    vp_levels = profile_levels(df, lookback=max(lookback, 100))

    supports = sorted(set(lows + fvg_sup + vp_levels + [liq_lo]))
    resistances = sorted(set(highs + fvg_res + vp_levels + [liq_hi]))
    return supports, resistances


def nearest_support(df: pd.DataFrame, price: float, window: int = 3) -> float | None:
    """Highest support strictly below ``price`` (a stop sits just under it)."""
    supports, _ = support_resistance(df, window)
    below = [s for s in supports if s < price]
    return max(below) if below else None


def nearest_resistance(df: pd.DataFrame, price: float, window: int = 3) -> float | None:
    """Lowest resistance strictly above ``price`` (a long target sits just under it)."""
    _, resistances = support_resistance(df, window)
    above = [r for r in resistances if r > price]
    return min(above) if above else None


def levels_summary(df: pd.DataFrame, window: int = 3) -> dict:
    """Convenience for audit/debugging."""
    s, r = support_resistance(df, window)
    price = float(df["close"].iloc[-1])
    return {
        "price": price,
        "nearest_support": nearest_support(df, price, window),
        "nearest_resistance": nearest_resistance(df, price, window),
        "n_supports": len(s),
        "n_resistances": len(r),
    }
