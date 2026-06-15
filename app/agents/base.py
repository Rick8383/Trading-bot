"""Analytic agent base class + score/probability helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from app.models import AgentVote


def vote_from_score(
    agent: str,
    asset: str,
    role: str,
    score: float,
    confidence: float,
    reasoning: str = "",
    risk_flags: list[str] | None = None,
    features: dict | None = None,
) -> AgentVote:
    """Convert a directional score in [-100, 100] into a probability vote.

    A score of +100 -> buy≈1; -100 -> sell≈1; 0 -> mostly hold. The mapping is
    smooth so the conviction engine sees graded opinions, not hard flips.
    """
    s = max(-100.0, min(100.0, score))
    mag = abs(s) / 100.0
    hold = 1.0 - mag
    buy = mag if s > 0 else 0.0
    sell = mag if s < 0 else 0.0
    total = buy + sell + hold or 1.0
    return AgentVote(
        agent=agent,
        asset=asset,
        buy=buy / total,
        sell=sell / total,
        hold=hold / total,
        score=s,
        confidence=max(0.0, min(1.0, confidence)),
        reasoning=reasoning,
        risk_flags=risk_flags or [],
        features={"role": role, **(features or {})},
    )


class AnalyticAgent(ABC):
    """Base class for every score-producing agent.

    Subclasses implement :meth:`analyze` and declare a ``role`` used by the
    conviction engine's weight table.
    """

    name: str = "analytic"
    role: str = "other"

    @abstractmethod
    def analyze(self, asset: str, data: dict[str, pd.DataFrame]) -> AgentVote:
        """Return a vote given multi-timeframe enriched OHLCV frames.

        ``data`` maps timeframe label ("1D", "4H", ...) -> indicator-enriched
        DataFrame. Agents must be pure: no side effects, no order placement.
        """

    # Convenience for subclasses.
    def _vote(self, asset: str, score: float, confidence: float, reasoning: str = "",
              risk_flags: list[str] | None = None, features: dict | None = None) -> AgentVote:
        return vote_from_score(
            self.name, asset, self.role, score, confidence, reasoning, risk_flags, features
        )
