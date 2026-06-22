"""Momentum agent — RSI, MACD, ROC, ADX-weighted."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.agents.base import AnalyticAgent
from app.models import AgentVote


class MomentumAgent(AnalyticAgent):
    name = "MomentumAI"
    role = "momentum"

    def analyze(self, asset: str, data: dict[str, pd.DataFrame]) -> AgentVote:
        df = data.get("1D")
        if df is None:
            df = next(v for k, v in data.items() if k != "_context")
        if len(df) < 30:
            return self._vote(asset, 0.0, 0.2, "insufficient data")
        last = df.iloc[-1]

        rsi = last.get("rsi", 50.0)
        macd_hist = last.get("macd_hist", 0.0)
        roc = last.get("roc", 0.0)
        adx = last.get("adx", 0.0)

        # RSI centered at 50 -> [-100,100] contribution.
        rsi_score = (rsi - 50) / 50 * 100 if not pd.isna(rsi) else 0.0
        # MACD histogram sign & magnitude (normalized by price).
        macd_score = float(np.clip(macd_hist / last["close"] * 5000, -100, 100)) if not pd.isna(macd_hist) else 0.0
        roc_score = float(np.clip(roc * 5, -100, 100)) if not pd.isna(roc) else 0.0

        raw = 0.45 * rsi_score + 0.35 * macd_score + 0.20 * roc_score

        # ADX scales confidence (momentum matters more in trending markets).
        confidence = float(np.clip(0.3 + (adx / 100 if not pd.isna(adx) else 0.0), 0.2, 0.9))

        flags = []
        if not pd.isna(rsi) and (rsi > 80 or rsi < 20):
            flags.append("rsi_extreme")  # exhaustion risk
        reasoning = f"RSI={rsi:.0f} MACDhist={macd_hist:.3f} ROC={roc:.1f} ADX={adx:.0f}"
        return self._vote(asset, raw, confidence, reasoning, flags,
                          {"rsi": float(rsi), "adx": float(adx) if not pd.isna(adx) else None})
