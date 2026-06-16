"""Paper broker — simulated fills, positions, equity, and cash.

This is the default and only enabled broker. It tracks an internal ledger with
realistic costs so the founder can validate behavior on fictional capital, find
weaknesses, and feed outcomes to the learning loop — exactly the workflow the
spec demands before any real money is risked.

Accounting model (no leverage by default):
  * ``cash`` is free realized cash.
  * Opening a LONG debits cash by notional+commission; its market value is
    ``qty * price``.
  * Opening a SHORT debits only the commission; its contribution to equity is
    the unrealized PnL ``(entry - price) * qty`` (zero at entry).
  * ``equity = cash + Σ market_value(position)``.
This stays correct and intuitive for both directions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.constants import Action
from app.execution.order_validator import Order, validate
from app.execution.slippage import apply_costs


@dataclass
class Fill:
    symbol: str
    action: Action
    quantity: float
    price: float
    commission: float
    timestamp: datetime


@dataclass
class OpenPosition:
    symbol: str
    action: Action
    quantity: float
    entry: float
    stop_loss: float
    take_profit: float | None
    opened_at: datetime
    initial_stop: float = 0.0          # for R-multiple math (set on open)
    original_quantity: float = 0.0
    bars_held: int = 0
    moved_to_breakeven: bool = False
    scaled_out: bool = False

    def __post_init__(self) -> None:
        if self.initial_stop == 0.0:
            self.initial_stop = self.stop_loss
        if self.original_quantity == 0.0:
            self.original_quantity = self.quantity

    @property
    def risk_per_unit(self) -> float:
        return abs(self.entry - self.initial_stop)

    def r_multiple(self, price: float) -> float:
        """Open profit expressed in R (initial risk per unit)."""
        rpu = self.risk_per_unit
        if rpu <= 0:
            return 0.0
        direction = 1 if self.action == Action.LONG else -1
        return (price - self.entry) * direction / rpu

    def unrealized(self, price: float) -> float:
        direction = 1 if self.action == Action.LONG else -1
        return (price - self.entry) * self.quantity * direction

    def market_value(self, price: float) -> float:
        """Contribution of this position to equity."""
        if self.action == Action.LONG:
            return self.quantity * price          # cash already paid out
        return self.unrealized(price)             # short: only PnL counts


@dataclass
class ClosedTrade:
    symbol: str
    action: Action
    quantity: float
    entry: float
    exit: float
    pnl: float
    return_pct: float
    opened_at: datetime
    closed_at: datetime
    reason: str
    decision_ref: str | None = None


@dataclass
class PaperBroker:
    cash: float
    slippage_bps: float = 5
    commission_bps: float = 2
    max_leverage: float = 1.0
    positions: dict[str, OpenPosition] = field(default_factory=dict)
    fills: list[Fill] = field(default_factory=list)
    closed: list[ClosedTrade] = field(default_factory=list)
    _start_equity: float = field(default=0.0)

    def __post_init__(self) -> None:
        self._start_equity = self.cash

    # --- queries -------------------------------------------------------
    def equity(self, marks: dict[str, float]) -> float:
        return self.cash + sum(
            p.market_value(marks.get(p.symbol, p.entry)) for p in self.positions.values()
        )

    @property
    def start_equity(self) -> float:
        return self._start_equity

    # --- mutations -----------------------------------------------------
    def submit(self, order: Order, decision_ref: str | None = None) -> Fill:
        validate(order, self.max_leverage)
        fill_price, comm_frac = apply_costs(
            order.entry, order.action, self.slippage_bps, self.commission_bps
        )
        notional = fill_price * order.quantity
        commission = notional * comm_frac

        if order.action == Action.LONG:
            if notional + commission > self.cash + 1e-6:
                raise ValueError("insufficient cash for long order (no leverage)")
            self.cash -= notional + commission
        else:  # SHORT: pay only the fee up front
            self.cash -= commission

        self.positions[order.symbol] = OpenPosition(
            symbol=order.symbol, action=order.action, quantity=order.quantity,
            entry=fill_price, stop_loss=order.stop_loss, take_profit=order.take_profit,
            opened_at=datetime.now(timezone.utc),
        )
        fill = Fill(order.symbol, order.action, order.quantity, fill_price, commission,
                    datetime.now(timezone.utc))
        self.fills.append(fill)
        self._last_ref = decision_ref
        return fill

    def close(self, symbol: str, price: float, reason: str = "manual") -> ClosedTrade | None:
        pos = self.positions.pop(symbol, None)
        if pos is None:
            return None
        exit_action = Action.SHORT if pos.action == Action.LONG else Action.LONG
        fill_price, comm_frac = apply_costs(price, exit_action, self.slippage_bps, self.commission_bps)
        notional = fill_price * pos.quantity
        commission = notional * comm_frac
        direction = 1 if pos.action == Action.LONG else -1
        pnl = (fill_price - pos.entry) * pos.quantity * direction - commission

        if pos.action == Action.LONG:
            self.cash += notional - commission           # recover proceeds
        else:
            self.cash += pnl                              # settle short PnL

        ret = pnl / (pos.entry * pos.quantity) if pos.quantity else 0.0
        trade = ClosedTrade(
            symbol=symbol, action=pos.action, quantity=pos.quantity, entry=pos.entry,
            exit=fill_price, pnl=pnl, return_pct=ret, opened_at=pos.opened_at,
            closed_at=datetime.now(timezone.utc), reason=reason,
        )
        self.closed.append(trade)
        return trade

    def partial_close(self, symbol: str, fraction: float, price: float,
                      reason: str = "scale_out") -> ClosedTrade | None:
        """Close ``fraction`` of a position, leaving the rest open (a runner)."""
        pos = self.positions.get(symbol)
        if pos is None:
            return None
        fraction = max(0.0, min(1.0, fraction))
        qty = pos.quantity * fraction
        if qty <= 0:
            return None
        exit_action = Action.SHORT if pos.action == Action.LONG else Action.LONG
        fill_price, comm_frac = apply_costs(price, exit_action, self.slippage_bps, self.commission_bps)
        notional = fill_price * qty
        commission = notional * comm_frac
        direction = 1 if pos.action == Action.LONG else -1
        pnl = (fill_price - pos.entry) * qty * direction - commission
        self.cash += (notional - commission) if pos.action == Action.LONG else pnl

        pos.quantity -= qty
        pos.scaled_out = True
        ret = pnl / (pos.entry * qty) if qty else 0.0
        trade = ClosedTrade(symbol=symbol, action=pos.action, quantity=qty, entry=pos.entry,
                            exit=fill_price, pnl=pnl, return_pct=ret, opened_at=pos.opened_at,
                            closed_at=datetime.now(timezone.utc), reason=reason)
        self.closed.append(trade)
        if pos.quantity <= 1e-9:
            self.positions.pop(symbol, None)
        return trade

    def mark_to_market(self, marks: dict[str, float]) -> list[ClosedTrade]:
        """Check stops/targets against current marks and auto-close any hits."""
        closed: list[ClosedTrade] = []
        for symbol, pos in list(self.positions.items()):
            price = marks.get(symbol)
            if price is None:
                continue
            if pos.action == Action.LONG:
                if price <= pos.stop_loss:
                    closed.append(self.close(symbol, pos.stop_loss, "stop_loss"))
                elif pos.take_profit and price >= pos.take_profit:
                    closed.append(self.close(symbol, pos.take_profit, "take_profit"))
            else:
                if price >= pos.stop_loss:
                    closed.append(self.close(symbol, pos.stop_loss, "stop_loss"))
                elif pos.take_profit and price <= pos.take_profit:
                    closed.append(self.close(symbol, pos.take_profit, "take_profit"))
        return [c for c in closed if c]
