from app.core.constants import MarketRegime
from app.decision.adaptive_risk import adapt_risk
from app.decision.capital_preservation import evaluate_drawdown, recovery_exposure
from app.decision.conviction import allocation_factor, compute_conviction, conviction_band
from app.decision.expected_value import evaluate, expected_value, reward_risk


def test_expected_value_sign():
    # Spec example: 55% win, +8% gain, 45% loss, -3% -> ~+3.05
    assert round(expected_value(0.55, 8, 3), 2) == 3.05
    assert expected_value(0.4, 2, 5) < 0


def test_reward_risk_and_gate():
    assert reward_risk(100, 95, 110) == 2.0
    # RR below the floor is rejected.
    res = evaluate(win_prob=0.55, entry=100, stop=97, target=104, min_rr=2.0)
    assert not res.accept
    # A 2.5 RR with positive EV passes.
    ok = evaluate(win_prob=0.55, entry=100, stop=96, target=110, min_rr=2.0)
    assert ok.accept and ok.expected_value > 0


def test_conviction_blend_and_bands():
    scores = {"trend": 80, "momentum": 60, "regime": 50}
    c = compute_conviction(scores)
    assert 50 <= c <= 80
    assert conviction_band(30) == "NO_TRADE"
    assert conviction_band(90) == "HIGH_CONVICTION"


def test_allocation_is_progressive_not_binary():
    # No cliff between 79 and 80.
    a79 = allocation_factor(79)
    a80 = allocation_factor(80)
    assert abs(a80 - a79) < 0.05
    assert allocation_factor(30) == 0.0
    assert allocation_factor(100) <= 1.0
    # Monotonic non-decreasing across the range.
    vals = [allocation_factor(x) for x in range(0, 101, 5)]
    assert all(b >= a - 1e-9 for a, b in zip(vals, vals[1:]))


def test_drawdown_ladder_and_kill():
    s5 = evaluate_drawdown(0.06)
    assert s5.max_exposure == 0.75
    s10 = evaluate_drawdown(0.11)
    assert s10.max_exposure == 0.0 and s10.paper_only
    s15 = evaluate_drawdown(0.16)
    assert s15.kill_switch


def test_recovery_ramps_slowly():
    assert recovery_exposure(0.11) == 0.25
    assert recovery_exposure(0.0) == 1.0


def test_adaptive_risk_never_increases_after_wins():
    base = 0.0075
    rp = adapt_risk(base_risk=base, regime=MarketRegime.BULL, consecutive_losses=0)
    assert rp.risk_per_trade <= base
    # Losses reduce risk.
    rp_loss = adapt_risk(base_risk=base, regime=MarketRegime.BULL, consecutive_losses=3)
    assert rp_loss.risk_per_trade < rp.risk_per_trade
    # High volatility reduces risk and caps exposure.
    rp_hv = adapt_risk(base_risk=base, regime=MarketRegime.HIGH_VOL, realized_vol=0.6)
    assert rp_hv.risk_per_trade < base and rp_hv.gross_exposure_cap <= 0.5


def test_crash_regime_zeroes_risk():
    rp = adapt_risk(base_risk=0.0075, regime=MarketRegime.CRASH)
    assert rp.risk_per_trade == 0.0 and rp.gross_exposure_cap == 0.0
