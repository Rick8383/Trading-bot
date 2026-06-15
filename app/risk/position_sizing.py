"""Position sizing — risk-based, never notional-based.

We size from the *distance to the stop*, so every position risks the same
fraction of equity regardless of the asset's price or volatility. This is the
single most important sizing discipline in the system.
"""

from __future__ import annotations


def calculate_position_size(
    capital: float,
    risk_pct: float,
    entry_price: float,
    stop_price: float,
    allocation_factor: float = 1.0,
    max_asset_weight: float = 1.0,
) -> float:
    """Return the position size (units) honoring per-trade risk and the cap.

    * risk_pct: fraction of equity to risk if the stop is hit (e.g. 0.0075).
    * allocation_factor: conviction modulation in [0,1] (shrinks size only).
    * max_asset_weight: hard cap on notional weight for a single asset.
    """
    if entry_price <= 0:
        return 0.0
    stop_distance = abs(entry_price - stop_price)
    if stop_distance <= 0:
        return 0.0  # undefined risk -> no trade (a missing stop must never size)

    risk_amount = capital * risk_pct * max(0.0, min(1.0, allocation_factor))
    size = risk_amount / stop_distance

    # Clamp to the per-asset notional cap.
    max_notional = capital * max_asset_weight
    if size * entry_price > max_notional:
        size = max_notional / entry_price
    return float(max(0.0, size))


def position_weight(size: float, entry_price: float, capital: float) -> float:
    """Notional weight of a position as a fraction of equity."""
    if capital <= 0:
        return 0.0
    return (size * entry_price) / capital
