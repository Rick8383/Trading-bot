"""Pre-trade order validation — the last gate before a fill.

Defense in depth: even if upstream logic erred, these asserts refuse to place a
stopless, zero-quantity, or leverage-violating order. A missing stop must NEVER
reach the broker.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.constants import Action
from app.core.exceptions import OrderRejected


@dataclass
class Order:
    symbol: str
    action: Action
    quantity: float
    entry: float
    stop_loss: float | None
    take_profit: float | None = None
    leverage: float = 1.0


def validate(order: Order, max_leverage: float = 1.0) -> Order:
    if not order.symbol:
        raise OrderRejected("missing symbol")
    if order.action == Action.FLAT:
        raise OrderRejected("cannot place a FLAT order")
    if order.quantity <= 0:
        raise OrderRejected(f"non-positive quantity: {order.quantity}")
    if order.entry <= 0:
        raise OrderRejected(f"invalid entry price: {order.entry}")
    if order.stop_loss is None or order.stop_loss <= 0:
        raise OrderRejected("missing stop loss — refused")  # the cardinal rule
    if abs(order.entry - order.stop_loss) <= 0:
        raise OrderRejected("zero stop distance — undefined risk")
    if order.leverage > max_leverage + 1e-9:
        raise OrderRejected(f"leverage {order.leverage} > max {max_leverage}")
    # Stop must be on the correct side of entry.
    if order.action == Action.LONG and order.stop_loss >= order.entry:
        raise OrderRejected("long stop must be below entry")
    if order.action == Action.SHORT and order.stop_loss <= order.entry:
        raise OrderRejected("short stop must be above entry")
    return order
