"""Volume Profile & anchored VWAP — liquidity-based price levels.

Where price traded the most volume is where the market agrees on value; those
high-volume nodes act as magnets and as support/resistance far more reliably
than a single swing point. We expose:

  * Point of Control (POC)      — the highest-volume price.
  * Value Area High/Low (VAH/VAL) — the band holding ~70% of volume.
  * Anchored VWAP               — volume-weighted average price from an anchor.

Pure pandas/numpy, deterministic. Feeds both the structure-level stops/targets
and a dedicated agent.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class VolumeProfile:
    poc: float            # point of control (price of max volume)
    vah: float            # value-area high
    val: float            # value-area low
    hvn: list[float]      # high-volume nodes (top buckets)


def volume_profile(df: pd.DataFrame, bins: int = 24, lookback: int = 120,
                   value_area_pct: float = 0.70) -> VolumeProfile | None:
    """Build a volume-by-price histogram over the recent window."""
    recent = df.tail(lookback)
    if len(recent) < 20:
        return None
    typical = (recent["high"] + recent["low"] + recent["close"]) / 3
    vol = recent["volume"].to_numpy(dtype=float)
    lo, hi = float(typical.min()), float(typical.max())
    if hi <= lo:
        return None

    edges = np.linspace(lo, hi, bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2
    idx = np.clip(np.digitize(typical.to_numpy(), edges) - 1, 0, bins - 1)
    hist = np.zeros(bins)
    for i, v in zip(idx, vol):
        hist[i] += v
    if hist.sum() <= 0:
        return None

    poc_i = int(np.argmax(hist))
    poc = float(centers[poc_i])

    # Value area: grow outward from the POC until ~value_area_pct of volume.
    order = np.argsort(hist)[::-1]
    target = value_area_pct * hist.sum()
    chosen, acc = [], 0.0
    for b in order:
        chosen.append(b)
        acc += hist[b]
        if acc >= target:
            break
    va_prices = centers[chosen]
    vah, val = float(va_prices.max()), float(va_prices.min())
    hvn = [float(centers[b]) for b in order[:3]]
    return VolumeProfile(poc=poc, vah=vah, val=val, hvn=hvn)


def anchored_vwap(df: pd.DataFrame, anchor_bars: int = 60) -> float | None:
    """VWAP computed from ``anchor_bars`` ago to the latest bar."""
    seg = df.tail(max(anchor_bars, 5))
    typical = (seg["high"] + seg["low"] + seg["close"]) / 3
    vol = seg["volume"]
    denom = vol.cumsum().iloc[-1]
    if denom <= 0:
        return None
    return float((typical * vol).cumsum().iloc[-1] / denom)


def profile_levels(df: pd.DataFrame, bins: int = 24, lookback: int = 120) -> list[float]:
    """POC + value-area edges as extra support/resistance candidates."""
    vp = volume_profile(df, bins, lookback)
    if vp is None:
        return []
    return [vp.poc, vp.vah, vp.val]
