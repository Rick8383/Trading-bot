"""Stop-loss and take-profit construction + trailing logic.

Rules enforced by code, not by hope:
  * Every trade has a stop. (Validated again in execution.)
  * Stops only move in the favorable direction (never widened).
"""

from __future__ import annotations

from app.core.constants import Action


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


def trail_stop(
    current_stop: float, price: float, atr: float, action: Action, multiplier: float = 2.5
) -> float:
    """Ratchet the stop toward price; only ever tightens (favorable side)."""
    candidate = atr_stop(price, atr, action, multiplier)
    if action == Action.LONG:
        return max(current_stop, candidate)   # long: stop only moves up
    return min(current_stop, candidate)       # short: stop only moves down
