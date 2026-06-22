"""Shared enumerations and constant labels used across the system."""

from __future__ import annotations

from enum import Enum


class Action(str, Enum):
    """Final directional decision for an asset."""

    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class Vote(str, Enum):
    """An analytic agent's directional opinion."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class MarketRegime(str, Enum):
    """Coarse market state classification."""

    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    HIGH_VOL = "high_vol"
    CRASH = "crash"
    RECOVERY = "recovery"


class Timeframe(str, Enum):
    H1 = "1H"
    H4 = "4H"
    D1 = "1D"
    W1 = "1W"


# Multi-timeframe blend weights (longer horizons dominate the bias).
TIMEFRAME_WEIGHTS: dict[str, float] = {
    "1H": 0.15,
    "4H": 0.25,
    "1D": 0.35,
    "1W": 0.25,
}

# Conviction band labels (used by monitoring/audit, not for sizing math).
CONVICTION_NO_TRADE = "NO_TRADE"
CONVICTION_WATCHLIST = "WATCHLIST"
CONVICTION_VALID = "VALID_SIGNAL"
CONVICTION_HIGH = "HIGH_CONVICTION"
