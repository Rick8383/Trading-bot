"""Social sentiment agent — euphoria / panic / capitulation detector.

Reads context["sentiment"][asset] in [-100, 100] from a SentimentProvider
(Reddit/X/forums). Extreme readings are treated as *contrarian* risk flags:
euphoria near tops and panic near bottoms both warrant caution, so this agent
dampens conviction at the extremes rather than chasing the crowd.
"""

from __future__ import annotations

import pandas as pd

from app.agents.base import AnalyticAgent
from app.models import AgentVote


class SocialSentimentAgent(AnalyticAgent):
    name = "SocialSentimentAI"
    role = "sentiment"

    def analyze(self, asset: str, data: dict[str, pd.DataFrame]) -> AgentVote:
        ctx = data.get("_context") or {}
        s = (ctx.get("sentiment") or {}).get(asset)
        if s is None:
            return self._vote(asset, 0.0, 0.2, "social: no feed (neutral)")
        s = max(-100.0, min(100.0, float(s)))

        flags: list[str] = []
        # Contrarian damping at extremes (euphoria/panic are exhaustion signals).
        if s > 70:
            flags.append("euphoria")
            score = s * 0.3 - 20      # temper bullishness near euphoria
        elif s < -70:
            flags.append("panic")
            score = s * 0.3 + 20      # temper bearishness near capitulation
        else:
            score = s * 0.5           # moderate readings: mild momentum confirm
        return self._vote(asset, float(max(-100, min(100, score))), 0.35,
                          f"social={s:+.0f}{' (' + ','.join(flags) + ')' if flags else ''}",
                          flags, {"sentiment": s})
