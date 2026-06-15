"""The Risk Manager — absolute veto authority.

No analytic agent, and not even the CIO, may override a hard risk veto. This
class is intentionally boring and strict: it says NO often, and that is the
point. It returns a structured verdict so the audit log records *why*.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import RiskConfig
from app.core.constants import Action
from app.decision.capital_preservation import PreservationState
from app.decision.exposure import Position, can_add
from app.models import TradeIdea


@dataclass
class RiskVerdict:
    approved: bool
    reasons: list[str] = field(default_factory=list)
    adjustments: dict[str, float] = field(default_factory=dict)

    @property
    def reason(self) -> str:
        return "; ".join(self.reasons) if self.reasons else "approved"


class RiskManager:
    """Validates trade ideas against hard limits. Veto is final."""

    def __init__(self, risk: RiskConfig):
        self.risk = risk

    def validate(
        self,
        idea: TradeIdea,
        *,
        portfolio: list[Position],
        preservation: PreservationState,
        daily_loss: float,
        shorts_allowed: bool = True,
        exposure_cap: float | None = None,
    ) -> RiskVerdict:
        reasons: list[str] = []

        # 1) Kill switch / paper-only state.
        if preservation.kill_switch:
            return RiskVerdict(False, ["kill switch active"])
        if preservation.paper_only:
            reasons.append("paper-only state: no new risk")
            return RiskVerdict(False, reasons)

        # 2) Daily loss limit.
        if daily_loss >= self.risk.daily_loss_limit:
            return RiskVerdict(False, [f"daily loss {daily_loss:.1%} >= limit"])

        # 3) Stop must exist and define real risk.
        if idea.stop_loss is None or idea.stop_loss <= 0:
            return RiskVerdict(False, ["missing/invalid stop loss"])
        if abs(idea.entry - idea.stop_loss) <= 0:
            return RiskVerdict(False, ["zero stop distance (undefined risk)"])

        # 4) Reward/risk floor.
        if idea.reward_risk < self.risk.min_rr:
            return RiskVerdict(False, [f"RR {idea.reward_risk:.2f} < {self.risk.min_rr}"])

        # 5) Expected value must be positive.
        if idea.expected_value <= 0:
            return RiskVerdict(False, [f"EV {idea.expected_value:.3f} <= 0"])

        # 6) Shorts may be blocked by regime.
        if idea.action == Action.SHORT and not shorts_allowed:
            return RiskVerdict(False, ["shorts disabled in current regime"])

        # 7) Portfolio exposure feasibility.
        signed = idea.conviction / 100 * self.risk.max_asset_exposure
        weight = signed if idea.action == Action.LONG else -signed
        ok, why = can_add(portfolio, Position(idea.asset, idea.action, weight), self.risk, exposure_cap)
        if not ok:
            return RiskVerdict(False, [f"exposure: {why}"])

        return RiskVerdict(True, reasons or ["all hard limits satisfied"])
