"""Correlation-aware portfolio construction.

Twenty crypto names that all move together are not twenty bets — they are one.
This module measures how correlated a candidate is with what's already held and:
  * vetoes it when the average correlation exceeds a hard cap, and
  * otherwise shrinks its size in proportion to that correlation.

It also reports the *effective number of bets* (a diversification ratio) so the
CIO can see how concentrated the book really is.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.core.config import PortfolioConfig


def returns_matrix(daily: dict[str, pd.DataFrame], lookback: int = 60) -> pd.DataFrame:
    """Align recent close-to-close returns across the universe."""
    cols = {}
    for sym, df in daily.items():
        if df is None or len(df) < lookback + 2:
            continue
        cols[sym] = df["close"].pct_change().tail(lookback).reset_index(drop=True)
    if not cols:
        return pd.DataFrame()
    return pd.DataFrame(cols).dropna(how="all")


def correlation_matrix(daily: dict[str, pd.DataFrame], lookback: int = 60) -> pd.DataFrame:
    rets = returns_matrix(daily, lookback)
    if rets.shape[1] < 2:
        return pd.DataFrame()
    return rets.corr()


def avg_correlation(symbol: str, held: list[str], corr: pd.DataFrame) -> float:
    """Mean absolute correlation of ``symbol`` to the held names (0 if none)."""
    peers = [h for h in held if h != symbol and h in corr.columns and symbol in corr.index]
    if not peers or symbol not in corr.index:
        return 0.0
    vals = [abs(float(corr.at[symbol, h])) for h in peers if not np.isnan(corr.at[symbol, h])]
    return float(np.mean(vals)) if vals else 0.0


def correlation_scale(avg_corr: float, cfg: PortfolioConfig) -> float:
    """Size multiplier in [min_scale, 1]: less size the more correlated it is."""
    if avg_corr <= cfg.corr_threshold:
        return 1.0
    span = max(1e-9, 1.0 - cfg.corr_threshold)
    frac = (avg_corr - cfg.corr_threshold) / span        # 0..1
    return float(max(cfg.min_scale, 1.0 - frac * (1.0 - cfg.min_scale)))


def assess_candidate(symbol: str, held: list[str], corr: pd.DataFrame,
                     cfg: PortfolioConfig) -> tuple[bool, float, str]:
    """Return (veto, size_scale, reason) for adding ``symbol`` to the book."""
    if not cfg.enabled or corr.empty or not held:
        return False, 1.0, "no correlation constraint"
    ac = avg_correlation(symbol, held, corr)
    if ac >= cfg.max_correlation:
        return True, 0.0, f"avg corr {ac:.2f} >= cap {cfg.max_correlation:.2f}"
    scale = correlation_scale(ac, cfg)
    return False, scale, f"avg corr {ac:.2f} -> size x{scale:.2f}"


def effective_bets(weights: dict[str, float], corr: pd.DataFrame) -> float:
    """Diversification ratio ~ effective number of independent positions.

    1.0 means everything is one bet; N means N uncorrelated bets. Uses the
    inverse Herfindahl of correlation-adjusted weights as a simple proxy.
    """
    syms = [s for s in weights if s in corr.columns]
    if not syms:
        return float(len([w for w in weights.values() if abs(w) > 0]))
    w = np.array([abs(weights[s]) for s in syms])
    if w.sum() <= 0:
        return 0.0
    w = w / w.sum()
    c = corr.loc[syms, syms].to_numpy()
    portfolio_var = float(w @ c @ w)
    if portfolio_var <= 0:
        return float(len(syms))
    return float(1.0 / portfolio_var)
