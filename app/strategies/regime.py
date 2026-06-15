"""Market regime classifier.

Probabilistic, never overconfident. Combines trend (price vs EMA200 + its
slope), trend strength (ADX), and volatility (realized vol vs its own history)
into one of the MarketRegime states, with a confidence score. The system is
explicitly allowed to be uncertain — low confidence should reduce exposure.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.core.constants import MarketRegime
from app.data import indicators as ind
from app.models import RegimeAssessment


def classify_regime(df: pd.DataFrame, lookback: int = 250) -> RegimeAssessment:
    """Classify the regime from an OHLCV frame (daily bars recommended)."""
    if len(df) < 60:
        return RegimeAssessment(
            regime=MarketRegime.SIDEWAYS, confidence=0.2, reasoning="insufficient history"
        )

    close = df["close"]
    ema200 = ind.ema(close, 200)
    adx = ind.adx(df["high"], df["low"], close).iloc[-1]
    rvol = ind.realized_volatility(close).iloc[-1]
    rvol_hist = ind.realized_volatility(close).tail(lookback)

    price = float(close.iloc[-1])
    ema_now = float(ema200.iloc[-1]) if not np.isnan(ema200.iloc[-1]) else price
    # EMA200 slope over ~20 bars, normalized by price.
    ema_slope = float((ema200.iloc[-1] - ema200.iloc[-21]) / price) if len(ema200) > 21 else 0.0

    above = price > ema_now
    adx_strong = (not np.isnan(adx)) and adx > 25
    vol_pct = float((rvol_hist < rvol).mean()) if len(rvol_hist.dropna()) > 10 else 0.5

    features = {
        "price_vs_ema200": price / ema_now - 1,
        "ema200_slope": ema_slope,
        "adx": float(adx) if not np.isnan(adx) else None,
        "realized_vol": float(rvol) if not np.isnan(rvol) else None,
        "vol_percentile": vol_pct,
    }

    def assess(regime, confidence, reasoning):
        return RegimeAssessment(
            regime=regime, confidence=confidence, reasoning=reasoning, features=features
        )

    # Crash: sharp recent drawdown + high vol.
    recent_dd = float(price / close.tail(40).max() - 1)
    if recent_dd < -0.20 and vol_pct > 0.85:
        return assess(MarketRegime.CRASH, 0.8, f"recent dd {recent_dd:.0%}, vol p{vol_pct:.0%}")

    # High volatility regime dominates when vol is extreme.
    if vol_pct > 0.90:
        return assess(MarketRegime.HIGH_VOL, min(0.9, vol_pct), f"vol percentile {vol_pct:.0%}")

    # Trend regimes need price/EMA alignment AND slope AND ADX strength.
    if above and ema_slope > 0.005 and adx_strong:
        conf = _conf(adx, vol_pct, aligned=True)
        # Recovery if we were recently deep underwater but now turning up.
        if recent_dd < -0.10:
            return assess(MarketRegime.RECOVERY, conf * 0.9, "turning up off lows")
        return assess(MarketRegime.BULL, conf, "price>EMA200, +slope, strong ADX")

    if (not above) and ema_slope < -0.005 and adx_strong:
        return assess(MarketRegime.BEAR, _conf(adx, vol_pct, aligned=True), "price<EMA200, -slope, strong ADX")

    # Otherwise: range / no clear trend.
    return assess(MarketRegime.SIDEWAYS, 0.5, "no dominant trend")


def _conf(adx: float, vol_pct: float, aligned: bool) -> float:
    base = 0.5
    if not np.isnan(adx):
        base += min(0.3, (adx - 25) / 100)
    base += 0.1 if aligned else 0.0
    base -= 0.1 * max(0.0, vol_pct - 0.7)  # penalize confidence in high vol
    return float(max(0.2, min(0.95, base)))
