import pytest

from app.core.constants import Action
from app.decision.capital_preservation import evaluate_drawdown
from app.decision.exposure import Position, can_add, check_limits
from app.models import TradeIdea
from app.risk.drawdown_guard import DrawdownGuard
from app.risk.position_sizing import calculate_position_size, position_weight
from app.risk.risk_manager import RiskManager
from app.risk.stop_manager import atr_stop, take_profit, trail_stop


def test_position_size_from_stop_distance():
    # Risk $1000 (1% of 100k) over a $5 stop distance -> 200 units.
    size = calculate_position_size(100_000, 0.01, 100, 95, allocation_factor=1.0, max_asset_weight=1.0)
    assert size == pytest.approx(200, rel=1e-6)


def test_position_size_zero_without_stop():
    assert calculate_position_size(100_000, 0.01, 100, 100) == 0.0


def test_position_size_respects_asset_cap():
    size = calculate_position_size(100_000, 0.01, 100, 99.9, allocation_factor=1.0, max_asset_weight=0.10)
    assert position_weight(size, 100, 100_000) <= 0.10 + 1e-9


def test_allocation_factor_only_shrinks():
    full = calculate_position_size(100_000, 0.01, 100, 95, allocation_factor=1.0)
    half = calculate_position_size(100_000, 0.01, 100, 95, allocation_factor=0.5)
    assert half == pytest.approx(full * 0.5, rel=1e-6)


def test_stops_on_correct_side():
    assert atr_stop(100, 2, Action.LONG, 2.5) == 95
    assert atr_stop(100, 2, Action.SHORT, 2.5) == 105
    assert take_profit(100, 95, Action.LONG, 2.0) == 110


def test_trailing_stop_only_tightens():
    s = trail_stop(95, 110, 2, Action.LONG, 2.5)
    assert s >= 95  # long stop moved up
    s2 = trail_stop(95, 90, 2, Action.LONG, 2.5)
    assert s2 == 95  # never widened back down


def test_drawdown_guard_tracks_peak():
    g = DrawdownGuard(100_000, 100_000)
    g.update(110_000)
    g.update(99_000)
    assert g.drawdown == pytest.approx((110_000 - 99_000) / 110_000)


def test_exposure_limits(settings):
    risk = settings.risk
    positions = [Position("A", Action.LONG, 0.09), Position("B", Action.LONG, 0.09)]
    rep = check_limits(positions, risk)
    assert rep.ok
    ok, _ = can_add(positions, Position("C", Action.LONG, 0.20), risk)
    assert not ok  # exceeds per-asset cap


def _idea(**kw):
    base = dict(asset="X", action=Action.LONG, conviction=70, entry=100, stop_loss=96,
                take_profit=110, expected_value=1.5, reward_risk=2.5, win_probability=0.55)
    base.update(kw)
    return TradeIdea(**base)


def test_risk_manager_rejects_missing_stop(settings):
    rm = RiskManager(settings.risk)
    pres = evaluate_drawdown(0.0)
    idea = _idea(stop_loss=100)  # zero distance
    v = rm.validate(idea, portfolio=[], preservation=pres, daily_loss=0.0)
    assert not v.approved


def test_risk_manager_rejects_thin_rr_and_negative_ev(settings):
    rm = RiskManager(settings.risk)
    pres = evaluate_drawdown(0.0)
    assert not rm.validate(_idea(reward_risk=1.2), portfolio=[], preservation=pres, daily_loss=0.0).approved
    assert not rm.validate(_idea(expected_value=-0.1), portfolio=[], preservation=pres, daily_loss=0.0).approved


def test_risk_manager_vetoes_in_kill_and_daily_loss(settings):
    rm = RiskManager(settings.risk)
    killed = evaluate_drawdown(0.20)
    assert not rm.validate(_idea(), portfolio=[], preservation=killed, daily_loss=0.0).approved
    pres = evaluate_drawdown(0.0)
    assert not rm.validate(_idea(), portfolio=[], preservation=pres, daily_loss=0.05).approved


def test_risk_manager_blocks_shorts_when_disallowed(settings):
    rm = RiskManager(settings.risk)
    pres = evaluate_drawdown(0.0)
    idea = _idea(action=Action.SHORT, stop_loss=104, take_profit=90)
    v = rm.validate(idea, portfolio=[], preservation=pres, daily_loss=0.0, shorts_allowed=False)
    assert not v.approved


def test_risk_manager_approves_clean_trade(settings):
    rm = RiskManager(settings.risk)
    pres = evaluate_drawdown(0.0)
    v = rm.validate(_idea(), portfolio=[], preservation=pres, daily_loss=0.0)
    assert v.approved
