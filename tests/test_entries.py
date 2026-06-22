import pytest

from app.agents.cio_agent import CIOAgent
from app.core.config import load_config
from app.core.constants import Action
from app.data import indicators as ind
from app.data.market_data import trending_ohlcv
from app.execution.order_validator import Order
from app.execution.paper_broker import PaperBroker


def _cio():
    return CIOAgent(load_config())


def test_market_entry_when_not_extended():
    cio = _cio()
    df = ind.enrich(trending_ohlcv("X", 1, 200))
    price = float(df["close"].iloc[-1])
    atr = float(df["atr"].iloc[-1])
    # Price at EMA20 -> not extended -> market entry.
    df.loc[df.index[-1], "ema20"] = price
    entry, pending = cio._entry_price(df, price, atr, Action.LONG)
    assert entry == price and pending is False


def test_pullback_limit_when_extended_long():
    s = load_config()
    s.entries.mode = "pullback"          # pullback is now opt-in (market is default)
    cio = CIOAgent(s)
    df = ind.enrich(trending_ohlcv("X", 1, 200))
    price = float(df["close"].iloc[-1])
    atr = float(df["atr"].iloc[-1])
    df.loc[df.index[-1], "ema20"] = price - 5 * atr   # price far above EMA20
    entry, pending = cio._entry_price(df, price, atr, Action.LONG)
    assert pending is True
    assert entry < price                # limit sits down at the pullback zone


def test_pullback_disabled_returns_market():
    s = load_config()
    s.entries.enabled = False
    cio = CIOAgent(s)
    df = ind.enrich(trending_ohlcv("X", 1, 200))
    price = float(df["close"].iloc[-1])
    atr = float(df["atr"].iloc[-1])
    df.loc[df.index[-1], "ema20"] = price - 5 * atr
    entry, pending = cio._entry_price(df, price, atr, Action.LONG)
    assert pending is False and entry == price


def test_broker_limit_order_fills_when_reached():
    b = PaperBroker(cash=100_000, slippage_bps=0, commission_bps=0)
    order = Order("X", Action.LONG, 100, 95, stop_loss=90, take_profit=110)
    b.submit_limit(order, limit_price=95, expiry_bars=5)
    assert len(b.pending) == 1
    b.process_pending({"X": 100})          # above limit -> no fill yet
    assert len(b.pending) == 1 and "X" not in b.positions
    b.process_pending({"X": 94})           # touched limit -> fill
    assert "X" in b.positions and not b.pending
    assert b.positions["X"].entry == 95


def test_broker_limit_order_expires():
    b = PaperBroker(cash=100_000, slippage_bps=0, commission_bps=0)
    b.submit_limit(Order("X", Action.LONG, 100, 95, stop_loss=90), limit_price=95, expiry_bars=2)
    b.process_pending({"X": 100})
    b.process_pending({"X": 100})
    assert not b.pending and "X" not in b.positions  # expired unfilled
