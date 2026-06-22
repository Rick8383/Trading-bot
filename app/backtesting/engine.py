"""Lightweight event-driven backtest engine (no heavy deps).

Takes a price series and boolean long entry/exit signals, simulates fills with
realistic costs, and returns an equity curve + per-trade returns. ``vectorbt``
can be swapped in later for speed; this keeps Phase 1 fully self-contained and
testable.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    equity_curve: list[float]
    trade_returns: list[float]
    n_trades: int


def run_backtest(
    prices: pd.Series,
    entries: pd.Series,
    exits: pd.Series,
    initial: float = 100_000.0,
    fee_bps: float = 2.0,
    slippage_bps: float = 5.0,
) -> BacktestResult:
    """Long-only signal backtest. Enter on ``entries``, exit on ``exits``."""
    cost = (fee_bps + slippage_bps) / 10_000
    cash = initial
    units = 0.0
    entry_price = 0.0
    equity_curve: list[float] = []
    trade_returns: list[float] = []

    prices = prices.dropna()
    entries = entries.reindex(prices.index).fillna(False)
    exits = exits.reindex(prices.index).fillna(False)

    for ts, price in prices.items():
        if units == 0 and bool(entries.loc[ts]):
            fill = price * (1 + cost)
            units = cash / fill
            entry_price = fill
            cash = 0.0
        elif units > 0 and bool(exits.loc[ts]):
            fill = price * (1 - cost)
            cash = units * fill
            trade_returns.append(fill / entry_price - 1)
            units = 0.0
        equity_curve.append(cash + units * price)

    return BacktestResult(equity_curve, trade_returns, len(trade_returns))


def monte_carlo(trade_returns: list[float], n_sims: int = 1000, seed: int = 42) -> dict:
    """Bootstrap-resample trade returns to gauge robustness of the equity path.

    Returns the distribution of terminal multiples and max drawdowns — a check
    that results aren't a fragile artifact of one lucky ordering.
    """
    if not trade_returns:
        return {"terminal_median": 1.0, "terminal_p05": 1.0, "max_dd_p95": 0.0, "n_sims": 0}
    rng = np.random.default_rng(seed)
    arr = np.array(trade_returns)
    terminals, max_dds = [], []
    for _ in range(n_sims):
        sample = rng.choice(arr, size=len(arr), replace=True)
        curve = np.cumprod(1 + sample)
        terminals.append(curve[-1])
        peak = np.maximum.accumulate(curve)
        max_dds.append(float(np.max((peak - curve) / peak)))
    return {
        "terminal_median": float(np.median(terminals)),
        "terminal_p05": float(np.percentile(terminals, 5)),
        "terminal_p95": float(np.percentile(terminals, 95)),
        "max_dd_p95": float(np.percentile(max_dds, 95)),
        "n_sims": n_sims,
    }


def walk_forward_splits(n: int, train: int, test: int):
    """Yield (train_slice, test_slice) index ranges for walk-forward analysis."""
    start = 0
    while start + train + test <= n:
        yield slice(start, start + train), slice(start + train, start + train + test)
        start += test
