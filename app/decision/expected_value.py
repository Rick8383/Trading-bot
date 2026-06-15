"""Expected value & reward/risk gating.

A trade is only worth taking if its probability-weighted payoff is positive AND
its reward/risk clears the minimum. These two filters, applied honestly, are
what separate disciplined allocation from gambling.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EVResult:
    expected_value: float       # in the same % units as the gain/loss inputs
    reward_risk: float
    win_probability: float
    accept: bool
    reason: str


def expected_value(
    win_prob: float, gain_pct: float, loss_pct: float
) -> float:
    """EV = P(win) * gain - P(loss) * loss.

    gain_pct/loss_pct are magnitudes (positive). loss is subtracted.
    """
    loss_prob = 1.0 - win_prob
    return win_prob * abs(gain_pct) - loss_prob * abs(loss_pct)


def reward_risk(entry: float, stop: float, target: float) -> float:
    """Reward/risk from concrete price levels (direction-agnostic)."""
    risk = abs(entry - stop)
    reward = abs(target - entry)
    if risk <= 0:
        return 0.0
    return reward / risk


def evaluate(
    *,
    win_prob: float,
    entry: float,
    stop: float,
    target: float,
    min_rr: float,
) -> EVResult:
    """Full EV + RR gate. Returns an accept/reject verdict with a reason."""
    rr = reward_risk(entry, stop, target)
    risk_pct = abs(entry - stop) / entry * 100
    reward_pct = abs(target - entry) / entry * 100
    ev = expected_value(win_prob, reward_pct, risk_pct)

    if risk_pct <= 0:
        return EVResult(ev, rr, win_prob, False, "no stop distance (undefined risk)")
    if rr < min_rr:
        return EVResult(ev, rr, win_prob, False, f"reward/risk {rr:.2f} < min {min_rr}")
    if ev <= 0:
        return EVResult(ev, rr, win_prob, False, f"expected value {ev:.3f} <= 0")
    return EVResult(ev, rr, win_prob, True, "EV>0 and RR>=min")
