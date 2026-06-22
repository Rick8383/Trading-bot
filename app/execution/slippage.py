"""Realistic cost model: slippage + commission, applied on every fill.

Backtests and paper trading must pay the same costs a live account would, or
the whole exercise lies to us. Costs always work *against* the trader.
"""

from __future__ import annotations

from app.core.constants import Action


def apply_costs(
    price: float, action: Action, slippage_bps: float, commission_bps: float
) -> tuple[float, float]:
    """Return (fill_price, commission_fraction).

    Slippage moves the fill price adversely; commission is returned separately
    as a fraction of notional to be charged by the broker.
    """
    slip = price * slippage_bps / 10_000
    if action == Action.LONG:
        fill = price + slip      # buy worse (higher)
    elif action == Action.SHORT:
        fill = price - slip      # sell worse (lower)
    else:
        fill = price
    commission_fraction = commission_bps / 10_000
    return fill, commission_fraction
