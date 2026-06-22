import pytest

from app.core.config import ExitConfig
from app.core.constants import Action
from app.execution.exit_manager import manage_position
from app.execution.order_validator import Order
from app.execution.paper_broker import PaperBroker


def _broker_with_long():
    b = PaperBroker(cash=100_000, slippage_bps=0, commission_bps=0)
    # entry 100, stop 96 -> risk per unit = 4 ; qty 100
    b.submit(Order("X", Action.LONG, 100, 100, stop_loss=96, take_profit=120))
    return b


def test_r_multiple_and_partial_close():
    b = _broker_with_long()
    pos = b.positions["X"]
    assert pos.r_multiple(104) == pytest.approx(1.0)   # +4 over a 4 risk = 1R
    trade = b.partial_close("X", 0.5, 104, "scale_out")
    assert trade.quantity == pytest.approx(50)
    assert b.positions["X"].quantity == pytest.approx(50)
    assert b.positions["X"].scaled_out


def test_scale_out_and_breakeven_at_1r():
    b = _broker_with_long()
    pos = b.positions["X"]
    policy = ExitConfig()
    produced = manage_position(b, pos, 104, atr=2.0, policy=policy)  # at +1R
    assert produced and produced[0].reason == "scale_out"
    assert pos.quantity == pytest.approx(50)            # half banked
    assert pos.moved_to_breakeven and pos.stop_loss >= pos.entry  # BE protection


def test_trailing_only_tightens():
    b = _broker_with_long()
    pos = b.positions["X"]
    policy = ExitConfig(scale_out_fraction=0.0)         # isolate trailing
    manage_position(b, pos, 112, atr=2.0, policy=policy)  # +3R
    trailed = pos.stop_loss
    assert trailed > 96                                  # stop moved up
    # A pullback must not loosen the stop.
    manage_position(b, pos, 108, atr=2.0, policy=policy)
    assert pos.stop_loss == trailed


def test_time_stop_cuts_stagnant_trade():
    b = _broker_with_long()
    pos = b.positions["X"]
    pos.bars_held = 30
    policy = ExitConfig(time_stop_bars=25, time_stop_min_r=0.5)
    produced = manage_position(b, pos, 100.5, atr=2.0, policy=policy)  # ~0.1R, stale
    assert produced and produced[0].reason == "time_stop"
    assert "X" not in b.positions


def test_disabled_policy_is_noop():
    b = _broker_with_long()
    pos = b.positions["X"]
    assert manage_position(b, pos, 200, atr=2.0, policy=ExitConfig(enabled=False)) == []
    assert pos.quantity == 100
