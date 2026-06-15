"""Capital preservation: the drawdown ladder + recovery ramp.

Two ideas, both asymmetric on purpose:
  * As drawdown deepens, exposure is cut *fast* (defense).
  * As we recover, exposure is restored *slowly* (don't lunge back in).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import DrawdownRung


@dataclass(frozen=True)
class PreservationState:
    drawdown: float
    max_exposure: float       # cap on gross exposure, 0..1
    kill_switch: bool
    paper_only: bool
    reason: str


# Default ladder if config provides none. (dd threshold -> exposure cap)
DEFAULT_LADDER = [
    DrawdownRung(dd=0.05, exposure=0.75),
    DrawdownRung(dd=0.08, exposure=0.50),
    DrawdownRung(dd=0.10, exposure=0.00),
    DrawdownRung(dd=0.15, exposure=0.00),
]


def evaluate_drawdown(
    drawdown: float, ladder: list[DrawdownRung] | None = None, kill_dd: float = 0.15
) -> PreservationState:
    """Given current rolling drawdown (positive fraction), return the cap.

    ``drawdown`` is expressed as a positive number (0.07 == 7% below peak).
    """
    ladder = sorted(ladder or DEFAULT_LADDER, key=lambda r: r.dd)
    dd = max(0.0, drawdown)

    max_exposure = 1.0
    reason = "nominal"
    for rung in ladder:
        if dd >= rung.dd:
            max_exposure = rung.exposure
            reason = f"DD {dd:.1%} >= {rung.dd:.0%} -> exposure cap {rung.exposure:.0%}"

    kill = dd >= kill_dd
    paper_only = (max_exposure == 0.0) or kill
    if kill:
        reason = f"DD {dd:.1%} >= kill threshold {kill_dd:.0%} -> KILL SWITCH"
    return PreservationState(dd, max_exposure, kill, paper_only, reason)


def recovery_exposure(drawdown: float) -> float:
    """Slow ramp back as we climb out of a hole.

    Mirrors the spec's recovery ladder: deeper residual DD -> lower allowed
    exposure even while improving. Returns an exposure cap in {0.25,0.5,0.75,1}.
    """
    dd = max(0.0, drawdown)
    if dd >= 0.10:
        return 0.25
    if dd >= 0.08:
        return 0.50
    if dd >= 0.05:
        return 0.75
    return 1.0
