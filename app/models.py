"""Shared domain models — the contracts every layer speaks.

Keeping these in one place means the orchestration pipeline, the agents, the
risk layer and the audit log all agree on the exact shape of a vote and a
decision. Auditability depends on this.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.core.constants import Action, MarketRegime, Vote


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentVote(BaseModel):
    """A single analytic agent's opinion on one asset.

    ``buy``/``sell``/``hold`` are probabilities in [0, 1] that should sum to ~1.
    ``score`` is a normalized directional conviction in [-100, 100]
    (positive = bullish), derived from the probabilities. ``confidence`` in
    [0, 1] is how sure the agent is about its own read.
    """

    agent: str
    asset: str
    buy: float = Field(ge=0, le=1)
    sell: float = Field(ge=0, le=1)
    hold: float = Field(ge=0, le=1)
    score: float = Field(ge=-100, le=100, default=0.0)
    confidence: float = Field(ge=0, le=1, default=0.5)
    reasoning: str = ""
    risk_flags: list[str] = Field(default_factory=list)
    features: dict[str, Any] = Field(default_factory=dict)

    @property
    def direction(self) -> Vote:
        m = max(self.buy, self.sell, self.hold)
        if m == self.buy and self.buy >= self.sell:
            return Vote.BUY
        if m == self.sell:
            return Vote.SELL
        return Vote.HOLD


class RegimeAssessment(BaseModel):
    regime: MarketRegime
    confidence: float = Field(ge=0, le=1)
    reasoning: str = ""
    features: dict[str, Any] = Field(default_factory=dict)


class TradeIdea(BaseModel):
    """A candidate trade after scoring, before the risk veto / CIO sign-off."""

    asset: str
    action: Action
    conviction: float = Field(ge=0, le=100)
    entry: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    take_profit: float | None = None
    expected_value: float = 0.0
    reward_risk: float = 0.0
    win_probability: float = Field(ge=0, le=1, default=0.5)
    pending: bool = False                # True if entry is a pullback limit order
    votes: list[AgentVote] = Field(default_factory=list)


class FinalDecision(BaseModel):
    """The CIO's final, auditable verdict for one asset."""

    asset: str
    action: Action
    conviction: float = Field(ge=0, le=100, default=0.0)
    allocation: float = Field(ge=0, le=1, default=0.0)  # fraction of equity
    quantity: float = 0.0
    entry: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    expected_value: float = 0.0
    reward_risk: float = 0.0
    pending: bool = False                # entry is a pending pullback limit order
    rejected: bool = False
    rejection_reason: str | None = None
    regime: MarketRegime | None = None
    consulted_agents: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    learned_penalties: dict[str, float] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_utcnow)

    def audit_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
