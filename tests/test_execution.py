import pytest

from app.core.constants import Action
from app.execution.order_validator import Order, validate
from app.execution.paper_broker import PaperBroker
from app.execution.slippage import apply_costs
from app.core.exceptions import OrderRejected


def test_validator_refuses_stopless_order():
    o = Order("X", Action.LONG, 10, 100, stop_loss=None)
    with pytest.raises(OrderRejected):
        validate(o)


def test_validator_refuses_leverage():
    o = Order("X", Action.LONG, 10, 100, stop_loss=95, leverage=2.0)
    with pytest.raises(OrderRejected):
        validate(o, max_leverage=1.0)


def test_validator_checks_stop_side():
    with pytest.raises(OrderRejected):
        validate(Order("X", Action.LONG, 10, 100, stop_loss=105))  # long stop above entry


def test_slippage_is_adverse():
    buy, _ = apply_costs(100, Action.LONG, 5, 2)
    sell, _ = apply_costs(100, Action.SHORT, 5, 2)
    assert buy > 100 and sell < 100


def test_paper_broker_long_roundtrip_pnl():
    b = PaperBroker(cash=100_000, slippage_bps=0, commission_bps=0)
    b.submit(Order("X", Action.LONG, 100, 100, stop_loss=95, take_profit=120))
    assert b.cash == pytest.approx(90_000)
    trade = b.close("X", 110)
    assert trade.pnl == pytest.approx(1000)
    assert b.cash == pytest.approx(101_000)


def test_paper_broker_stop_autocloses():
    b = PaperBroker(cash=100_000, slippage_bps=0, commission_bps=0)
    b.submit(Order("X", Action.LONG, 100, 100, stop_loss=95, take_profit=120))
    closed = b.mark_to_market({"X": 94})
    assert closed and closed[0].reason == "stop_loss"
    assert "X" not in b.positions


def test_paper_broker_no_implicit_leverage():
    b = PaperBroker(cash=1000, slippage_bps=0, commission_bps=0)
    with pytest.raises(ValueError):
        b.submit(Order("X", Action.LONG, 100, 100, stop_loss=95))  # needs 10k, has 1k


def test_short_pnl_positive_when_price_falls():
    b = PaperBroker(cash=100_000, slippage_bps=0, commission_bps=0)
    b.submit(Order("X", Action.SHORT, 100, 100, stop_loss=105, take_profit=80))
    trade = b.close("X", 90)
    assert trade.pnl == pytest.approx(1000)
