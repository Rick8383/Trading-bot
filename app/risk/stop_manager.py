"""Stop-loss and take-profit construction + trailing logic.

Rules enforced by code, not by hope:
  * Every trade has a stop. (Validated again in execution.)
  * Stops only move in the favorable direction (never widened).

Two placement modes:
  * ATR mode — a fixed volatility multiple from entry (always available).
  * Structure mode — the stop sits just beyond the nearest support/resistance
    (a real invalidation level), *bounded* by ATR so it can never be absurdly
    tight or far. Targets sit at the next opposing level when that still clears
    the minimum reward/risk, else fall back to the RR-based target.
"""

from __future__ import annotations

import pandas as pd

from app.core.constants import Action
from app.strategies.structure_levels import nearest_resistance, nearest_support


def atr_stop(entry: float, atr: float, action: Action, multiplier: float = 2.5) -> float:
    """Volatility-based stop a fixed ATR-multiple away from entry."""
    dist = atr * multiplier
    if action == Action.LONG:
        return max(0.0, entry - dist)
    if action == Action.SHORT:
        return entry + dist
    raise ValueError("stop undefined for FLAT")


def take_profit(entry: float, stop: float, action: Action, rr: float = 2.0) -> float:
    """Target at a reward/risk multiple of the stop distance."""
    risk = abs(entry - stop)
    if action == Action.LONG:
        return entry + rr * risk
    if action == Action.SHORT:
        return entry - rr * risk
    raise ValueError("take-profit undefined for FLAT")


def structure_stop(
    df: pd.DataFrame,
    entry: float,
    atr: float,
    action: Action,
    multiplier: float = 2.5,
    buffer_atr: float = 0.25,
    sane_band: tuple[float, float] = (0.5, 3.0),
) -> float:
    """Stop placed just beyond the nearest structural level, bounded by ATR.

    The structural stop is used only when its distance is within
    ``sane_band × atr_distance`` — otherwise we fall back to the pure ATR stop.
    This keeps stops at meaningful invalidation levels without ever being
    absurdly tight (noise) or far (oversized risk).
    """
    atr_dist = atr * multiplier
    atr_level = atr_stop(entry, atr, action, multiplier)
    if atr <= 0 or atr_dist <= 0:
        return atr_level

    if action == Action.LONG:
        level = nearest_support(df, entry)
        if level is None:
            return atr_level
        candidate = level - buffer_atr * atr           # just under support
        dist = entry - candidate
    elif action == Action.SHORT:
        level = nearest_resistance(df, entry)
        if level is None:
            return atr_level
        candidate = level + buffer_atr * atr           # just above resistance
        dist = candidate - entry
    else:
        raise ValueError("stop undefined for FLAT")

    lo, hi = sane_band
    if not (lo * atr_dist <= dist <= hi * atr_dist):
        return atr_level                                # structure stop out of band
    return max(0.0, candidate) if action == Action.LONG else candidate


def structure_target(
    df: pd.DataFrame,
    entry: float,
    stop: float,
    action: Action,
    min_rr: float = 2.0,
) -> float:
    """Target at the next opposing level if it clears min RR, else RR-based."""
    rr_target = take_profit(entry, stop, action, min_rr)
    risk = abs(entry - stop)
    if risk <= 0:
        return rr_target

    if action == Action.LONG:
        level = nearest_resistance(df, entry)
        if level is not None and (level - entry) / risk >= min_rr:
            return level
    elif action == Action.SHORT:
        level = nearest_support(df, entry)
        if level is not None and (entry - level) / risk >= min_rr:
            return level
    return rr_target


def trail_stop(
    current_stop: float, price: float, atr: float, action: Action, multiplier: float = 2.5
) -> float:
    """Ratchet the stop toward price; only ever tightens (favorable side)."""
    candidate = atr_stop(price, atr, action, multiplier)
    if action == Action.LONG:
        return max(current_stop, candidate)   # long: stop only moves up
    return min(current_stop, candidate)       # short: stop only moves down
