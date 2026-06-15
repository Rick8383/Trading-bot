"""SMC agent — wraps the Smart Money Concepts detectors into a vote.

Role "pattern" and deliberately **low confidence**: these signals are nuanced
and noisy, so they nudge conviction rather than drive it.
"""

from __future__ import annotations

import pandas as pd

from app.agents.base import AnalyticAgent
from app.models import AgentVote
from app.strategies.smc import analyze_smc


class SMCAgent(AnalyticAgent):
    name = "SMC_AI"
    role = "pattern"

    def analyze(self, asset: str, data: dict[str, pd.DataFrame]) -> AgentVote:
        df = data.get("1D")
        if df is None:
            df = next(v for k, v in data.items() if k != "_context")
        sig = analyze_smc(df)
        reasoning = "SMC: " + (", ".join(sig.labels) if sig.labels else "no structure signal")
        # Low confidence by design (hard-to-detect patterns).
        return self._vote(asset, sig.score, 0.35, reasoning, [], {"smc_labels": sig.labels})
