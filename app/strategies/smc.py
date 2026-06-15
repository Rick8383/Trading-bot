"""Smart Money Concepts (SMC) detectors — deterministic, low-confidence.

BOS/CHOCH, Fair Value Gaps and liquidity sweeps. Per the founding spec these are
genuinely hard to detect reliably, so the SMC agent is **weighted low** and its
votes carry modest confidence. They add nuance, never dominate.

All functions are pure and operate on an OHLCV DataFrame with lowercase columns.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class SMCSignal:
    score: float            # [-100, 100], + bullish
    labels: list[str]


def _swings(high: pd.Series, low: pd.Series, window: int = 3):
    highs, lows = [], []
    h, l = high.values, low.values
    for i in range(window, len(h) - window):
        if h[i] == h[i - window:i + window + 1].max():
            highs.append((i, h[i]))
        if l[i] == l[i - window:i + window + 1].min():
            lows.append((i, l[i]))
    return highs, lows


def detect_fvg(df: pd.DataFrame, lookback: int = 30) -> tuple[float, str | None]:
    """Most recent 3-candle Fair Value Gap within lookback.

    Bullish FVG: low[i] > high[i-2] (unfilled gap up). Bearish: high[i] < low[i-2].
    """
    h, l = df["high"].values, df["low"].values
    start = max(2, len(df) - lookback)
    for i in range(len(df) - 1, start - 1, -1):
        if l[i] > h[i - 2]:
            return 35.0, "bullish_fvg"
        if h[i] < l[i - 2]:
            return -35.0, "bearish_fvg"
    return 0.0, None


def detect_bos_choch(df: pd.DataFrame, window: int = 3) -> tuple[float, str | None]:
    """Break of Structure / Change of Character from recent swings."""
    highs, lows = _swings(df["high"], df["low"], window)
    if len(highs) < 2 or len(lows) < 2:
        return 0.0, None
    close = df["close"].iloc[-1]
    last_sh, prev_sh = highs[-1][1], highs[-2][1]
    last_sl, prev_sl = lows[-1][1], lows[-2][1]

    # Break above last swing high.
    if close > last_sh:
        # CHOCH if structure had been making lower highs (downtrend flipping up).
        return (40.0, "bullish_choch") if last_sh < prev_sh else (30.0, "bullish_bos")
    if close < last_sl:
        return (-40.0, "bearish_choch") if last_sl > prev_sl else (-30.0, "bearish_bos")
    return 0.0, None


def detect_liquidity_sweep(df: pd.DataFrame, window: int = 3) -> tuple[float, str | None]:
    """Stop-hunt: wick takes out a prior swing then the candle closes back inside."""
    highs, lows = _swings(df["high"], df["low"], window)
    if not highs or not lows or len(df) < 2:
        return 0.0, None
    last = df.iloc[-1]
    prior_high = highs[-1][1]
    prior_low = lows[-1][1]
    # Swept highs then closed below -> bearish; swept lows then closed above -> bullish.
    if last["high"] > prior_high and last["close"] < prior_high:
        return -25.0, "bearish_sweep"
    if last["low"] < prior_low and last["close"] > prior_low:
        return 25.0, "bullish_sweep"
    return 0.0, None


def analyze_smc(df: pd.DataFrame) -> SMCSignal:
    if len(df) < 30:
        return SMCSignal(0.0, [])
    total = 0.0
    labels: list[str] = []
    for fn in (detect_fvg, detect_bos_choch, detect_liquidity_sweep):
        score, label = fn(df)
        total += score
        if label:
            labels.append(label)
    # Average the three detectors so the magnitude stays bounded/conservative.
    return SMCSignal(max(-100.0, min(100.0, total / 3)), labels)
