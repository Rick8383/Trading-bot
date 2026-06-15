"""Volume agent — OBV trend, volume spikes, VWAP distance."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.agents.base import AnalyticAgent
from app.models import AgentVote


class VolumeAgent(AnalyticAgent):
    name = "VolumeAI"
    role = "volume"

    def analyze(self, asset: str, data: dict[str, pd.DataFrame]) -> AgentVote:
        df = data.get("1D")
        if df is None:
            df = next(v for k, v in data.items() if k != "_context")
        if len(df) < 30:
            return self._vote(asset, 0.0, 0.2, "insufficient data")
        last = df.iloc[-1]

        # OBV slope over last 20 bars (normalized).
        obv = df["obv"].dropna()
        obv_score = 0.0
        if len(obv) > 20:
            slope = (obv.iloc[-1] - obv.iloc[-20]) / (abs(obv.iloc[-20]) + 1e-9)
            obv_score = float(np.clip(slope * 200, -60, 60))

        # Volume spike vs 20-bar average confirms conviction in the move's dir.
        vol_sma = last.get("vol_sma", np.nan)
        spike = (last["volume"] / vol_sma) if not pd.isna(vol_sma) and vol_sma > 0 else 1.0
        price_dir = np.sign(df["close"].diff().iloc[-1])
        spike_score = float(np.clip((spike - 1.0) * 40 * price_dir, -40, 40))

        score = 0.6 * obv_score + 0.4 * spike_score
        flags = ["volume_spike"] if spike > 1.8 else []
        reasoning = f"OBVscore={obv_score:.0f} volspike={spike:.2f}x"
        return self._vote(asset, score, 0.5, reasoning, flags, {"vol_spike": float(spike)})
