"""News agent — headline sentiment score per asset.

Reads a per-asset sentiment score injected into context["news"] (mapping
asset -> score in [-100, 100]) by a NewsProvider. With no feed connected it
abstains (neutral, low confidence) rather than inventing a signal.
"""

from __future__ import annotations

import pandas as pd

from app.agents.base import AnalyticAgent
from app.models import AgentVote


class NewsAgent(AnalyticAgent):
    name = "NewsAI"
    role = "news"

    def analyze(self, asset: str, data: dict[str, pd.DataFrame]) -> AgentVote:
        ctx = data.get("_context") or {}
        news = (ctx.get("news") or {}).get(asset)
        if news is None:
            return self._vote(asset, 0.0, 0.2, "news: no feed (neutral)")
        score = max(-100.0, min(100.0, float(news)))
        flags = ["adverse_news"] if score < -40 else []
        return self._vote(asset, score, 0.4, f"news sentiment={score:+.0f}", flags, {"news": score})
