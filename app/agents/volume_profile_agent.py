"""Volume Profile / anchored-VWAP agent.

Reads market acceptance rather than just price shape:
  * Above anchored VWAP -> demand in control (bullish bias), and vice-versa.
  * Above the value-area high -> acceptance higher (breakout continuation);
    below the value-area low -> acceptance lower (breakdown).
Role "volume", modest confidence — it confirms/tempers, it doesn't dominate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.agents.base import AnalyticAgent
from app.models import AgentVote
from app.strategies.volume_profile import anchored_vwap, volume_profile


class VolumeProfileAgent(AnalyticAgent):
    name = "VolumeProfileAI"
    role = "volume"

    def analyze(self, asset: str, data: dict[str, pd.DataFrame]) -> AgentVote:
        df = data.get("1D")
        if df is None:
            df = next(v for k, v in data.items() if k != "_context")
        if len(df) < 40:
            return self._vote(asset, 0.0, 0.2, "insufficient data")

        price = float(df["close"].iloc[-1])
        vp = volume_profile(df)
        vwap = anchored_vwap(df)
        if vp is None or vwap is None or vwap <= 0:
            return self._vote(asset, 0.0, 0.2, "no volume profile")

        # VWAP bias (normalized distance, capped).
        vwap_bias = float(np.clip((price / vwap - 1) * 400, -50, 50))

        # Value-area position.
        if price > vp.vah:
            va_bias, label = 35.0, "above VA (acceptance higher)"
        elif price < vp.val:
            va_bias, label = -35.0, "below VA (acceptance lower)"
        else:
            va_bias, label = 0.0, "inside value area"

        score = float(np.clip(vwap_bias + va_bias, -100, 100))
        reasoning = f"VWAP{'+' if price>=vwap else '-'} POC={vp.poc:.4g} {label}"
        return self._vote(asset, score, 0.45, reasoning, [],
                          {"poc": vp.poc, "vah": vp.vah, "val": vp.val, "avwap": vwap})
