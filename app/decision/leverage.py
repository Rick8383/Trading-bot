"""Conviction-gated, liquidation-safe leverage.

Three independent guards, ALL must pass for leverage > 1:
  1. enabled          — leverage is off unless explicitly turned on.
  2. conviction gate  — x5 only above conviction_x5, x10 only above conviction_x10.
  3. liquidation gate — the stop must sit inside ``liquidation_buffer / L`` of the
     entry, so the STOP closes a loser before the exchange liquidates. If the
     stop is too wide for a given leverage, leverage is reduced until safe.

Dollar risk per trade is hard-capped (``max_risk_per_trade``) so leverage
amplifies position size for high-conviction trades without enabling ruin.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.core.config import LeverageConfig


@dataclass(frozen=True)
class LeveragePlan:
    leverage: float          # 1.0 means unleveraged
    risk_pct: float          # effective per-trade risk fraction (capped)
    reason: str


def _conviction_leverage(conviction: float, cfg: LeverageConfig) -> float:
    if conviction >= cfg.conviction_x10:
        return min(10.0, cfg.max_leverage)
    if conviction >= cfg.conviction_x5:
        return min(5.0, cfg.max_leverage)
    return 1.0


def _liquidation_safe_leverage(entry: float, stop: float, cap: float, cfg: LeverageConfig) -> float:
    """Largest leverage (<= cap) for which the stop is inside the liq. distance."""
    if entry <= 0:
        return 1.0
    stop_frac = abs(entry - stop) / entry
    if stop_frac <= 0:
        return 1.0
    # Liquidation ~ at (1/L) adverse move; require stop_frac <= buffer / L.
    max_safe = cfg.liquidation_buffer / stop_frac
    return float(max(1.0, min(cap, math.floor(max_safe))))


def plan_leverage(
    *,
    conviction: float,
    entry: float,
    stop: float,
    base_risk_pct: float,
    cfg: LeverageConfig,
) -> LeveragePlan:
    """Decide leverage + effective risk for a trade. Safe, capped, gated."""
    if not cfg.enabled:
        return LeveragePlan(1.0, base_risk_pct, "leverage disabled")

    conv_lev = _conviction_leverage(conviction, cfg)
    if conv_lev <= 1.0:
        return LeveragePlan(1.0, base_risk_pct, f"conviction {conviction:.0f} below x5 gate")

    safe_lev = _liquidation_safe_leverage(entry, stop, conv_lev, cfg)
    if safe_lev <= 1.0:
        return LeveragePlan(1.0, base_risk_pct, "stop too wide for safe leverage")

    # Amplify dollar risk with leverage, but cap it hard.
    risk_pct = min(base_risk_pct * safe_lev, cfg.max_risk_per_trade)
    return LeveragePlan(
        leverage=safe_lev,
        risk_pct=risk_pct,
        reason=f"conviction {conviction:.0f} -> x{safe_lev:.0f} (risk {risk_pct:.1%}, liq-safe)",
    )
