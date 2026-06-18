"""Conviction-gated, liquidation-safe leverage + margin accounting + futures."""

import pytest

from app.core.config import LeverageConfig
from app.core.constants import Action
from app.core.exceptions import LiveTradingLocked, OrderRejected
from app.decision.leverage import plan_leverage
from app.execution.live_broker import CcxtFuturesBroker
from app.execution.order_validator import Order, validate
from app.execution.paper_broker import PaperBroker


def _cfg(**kw):
    base = dict(enabled=True, max_leverage=10, conviction_x5=70, conviction_x10=85,
                max_risk_per_trade=0.04, liquidation_buffer=0.80)
    base.update(kw)
    return LeverageConfig(**base)


def test_leverage_off_by_default():
    cfg = LeverageConfig()  # enabled defaults False
    plan = plan_leverage(conviction=95, entry=100, stop=98, base_risk_pct=0.01, cfg=cfg)
    assert plan.leverage == 1.0


def test_leverage_gated_by_conviction():
    cfg = _cfg()
    # Below x5 gate -> no leverage.
    assert plan_leverage(conviction=60, entry=100, stop=98, base_risk_pct=0.01, cfg=cfg).leverage == 1.0
    # 70-85 -> up to 5x (stop tight enough to be liq-safe).
    assert plan_leverage(conviction=75, entry=100, stop=99, base_risk_pct=0.01, cfg=cfg).leverage == 5.0
    # >=85 -> up to 10x.
    assert plan_leverage(conviction=90, entry=100, stop=99.5, base_risk_pct=0.01, cfg=cfg).leverage == 10.0


def test_leverage_reduced_when_stop_too_wide():
    cfg = _cfg()
    # Stop 10% away: at x10 liquidation (~8%) would hit first -> leverage capped.
    plan = plan_leverage(conviction=95, entry=100, stop=90, base_risk_pct=0.01, cfg=cfg)
    assert plan.leverage <= 8  # liquidation-safe: buffer/stop_frac = 0.8/0.10 = 8
    # The stop is inside the liquidation distance for the chosen leverage.
    assert (100 - 90) / 100 <= cfg.liquidation_buffer / plan.leverage + 1e-9


def test_leverage_caps_dollar_risk():
    cfg = _cfg(max_risk_per_trade=0.03)
    plan = plan_leverage(conviction=95, entry=100, stop=99.5, base_risk_pct=0.01, cfg=cfg)
    assert plan.risk_pct <= 0.03 + 1e-9        # never exceeds the hard cap


def test_validator_allows_leverage_within_cap_rejects_beyond():
    o = Order("X", Action.LONG, 10, 100, stop_loss=98, leverage=5)
    validate(o, max_leverage=10)               # ok
    with pytest.raises(OrderRejected):
        validate(Order("X", Action.LONG, 10, 100, stop_loss=98, leverage=12), max_leverage=10)


def test_paper_broker_margin_allows_leveraged_position():
    b = PaperBroker(cash=1000, slippage_bps=0, commission_bps=0, max_leverage=10)
    # Notional 5000 needs only 500 margin at 10x -> fits in 1000 cash.
    b.submit(Order("X", Action.LONG, 50, 100, stop_loss=98, leverage=10))
    assert b.positions["X"].margin == pytest.approx(500)
    assert b.cash == pytest.approx(500)
    # Leveraged PnL: +2 price * 50 = +100 on 500 margin.
    trade = b.close("X", 102)
    assert trade.pnl == pytest.approx(100)
    assert b.cash == pytest.approx(1100)       # margin 500 + pnl 100 returned


def test_paper_broker_rejects_insufficient_margin():
    b = PaperBroker(cash=100, slippage_bps=0, commission_bps=0, max_leverage=10)
    with pytest.raises(ValueError):
        b.submit(Order("X", Action.LONG, 50, 100, stop_loss=98, leverage=10))  # needs 500 margin


def test_unleveraged_long_unchanged():
    b = PaperBroker(cash=100_000, slippage_bps=0, commission_bps=0)
    b.submit(Order("X", Action.LONG, 100, 100, stop_loss=95, leverage=1))
    assert b.cash == pytest.approx(90_000)     # full notional as margin (spot-like)
    assert b.close("X", 110).pnl == pytest.approx(1000)


def test_futures_broker_locked_without_unlock():
    with pytest.raises(LiveTradingLocked):
        CcxtFuturesBroker("binance", "k", "s", unlocked=False)
