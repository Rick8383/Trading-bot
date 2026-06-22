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
    leverage: float = 1.0
    margin: float = 0.0                # cash posted as margin (notional / leverage)

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
        """Equity contribution = posted margin returned + unrealized PnL.

        Unified margin model: works for long, short and leveraged positions.
        For an unleveraged long, margin == notional, so this equals qty*price.
        """
        return self.margin + self.unrealized(price)


@dataclass
class PendingOrder:
    order: Order
    limit_price: float
    bars_left: int
    decision_ref: str | None = None


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
    pending: list[PendingOrder] = field(default_factory=list)
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
        leverage = max(1.0, order.leverage)
        notional = fill_price * order.quantity
        commission = notional * comm_frac
        margin = notional / leverage

        # Margin model: post margin (+ commission); cannot exceed available cash.
        if margin + commission > self.cash + 1e-6:
            raise ValueError("insufficient margin for order")
        self.cash -= margin + commission

        self.positions[order.symbol] = OpenPosition(
            symbol=order.symbol, action=order.action, quantity=order.quantity,
            entry=fill_price, stop_loss=order.stop_loss, take_profit=order.take_profit,
            opened_at=datetime.now(timezone.utc), leverage=leverage, margin=margin,
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
        # Return posted margin + settle PnL (margin model, leverage-aware).
        self.cash += pos.margin + pnl

        # Return on the *margin* committed (leverage amplifies the % return).
        ret = pnl / pos.margin if pos.margin else 0.0
        trade = ClosedTrade(
            symbol=symbol, action=pos.action, quantity=pos.quantity, entry=pos.entry,
            exit=fill_price, pnl=pnl, return_pct=ret, opened_at=pos.opened_at,
            closed_at=datetime.now(timezone.utc), reason=reason,
        )
        self.closed.append(trade)
        return trade

    def submit_limit(self, order: Order, limit_price: float, expiry_bars: int,
                     decision_ref: str | None = None) -> PendingOrder:
        """Queue a limit order (validated now, filled when price reaches the level)."""
        validate(order, self.max_leverage)
        po = PendingOrder(order, limit_price, max(1, expiry_bars), decision_ref)
        self.pending.append(po)
        return po

    def process_pending(self, marks: dict[str, float]) -> list[Fill]:
        """Fill limit orders whose level has been reached; expire stale ones."""
        fills: list[Fill] = []
        for po in list(self.pending):
            price = marks.get(po.order.symbol)
            if price is None:
                continue
            reached = (po.order.action == Action.LONG and price <= po.limit_price) or \
                      (po.order.action == Action.SHORT and price >= po.limit_price)
            if reached and po.order.symbol not in self.positions:
                po.order.entry = po.limit_price          # fill at the limit level
                try:
                    fills.append(self.submit(po.order, po.decision_ref))
                except ValueError:
                    pass                                  # insufficient cash -> drop
                self.pending.remove(po)
                continue
            po.bars_left -= 1
            if po.bars_left <= 0:
                self.pending.remove(po)                   # expired unfilled
        return fills

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
        margin_part = pos.margin * fraction
        self.cash += margin_part + pnl            # return proportional margin + PnL

        pos.quantity -= qty
        pos.margin -= margin_part
        pos.scaled_out = True
        ret = pnl / margin_part if margin_part else 0.0
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
