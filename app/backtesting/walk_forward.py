"""Walk-forward analysis — honest out-of-sample evaluation.

For each rolling split we pick the best parameter set on the *train* window, then
evaluate that choice on the *test* window only. OOS test segments are stitched
into one equity curve. This is the antidote to in-sample overfitting and the
single most important robustness check before risking anything.

Uses the dependency-light EMA-cross strategy as the optimization target; the
machinery generalizes to any signal generator.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from app.backtesting.engine import monte_carlo, run_backtest, walk_forward_splits
from app.data import indicators as ind
from app.monitoring.metrics import compute_report


@dataclass
class WindowResult:
    train: tuple[int, int]
    test: tuple[int, int]
    chosen_params: tuple[int, int]
    oos_return: float
    oos_trades: int


@dataclass
class WalkForwardReport:
    windows: list[WindowResult]
    oos_equity: list[float]
    oos_report: object
    monte_carlo: dict
    param_grid: list[tuple[int, int]] = field(default_factory=list)

    @property
    def selection_stability(self) -> float:
        """Fraction of windows that re-selected the most common parameter set."""
        if not self.windows:
            return 0.0
        from collections import Counter
        counts = Counter(w.chosen_params for w in self.windows)
        return counts.most_common(1)[0][1] / len(self.windows)


def _ema_signals(close: pd.Series, fast: int, slow: int):
    ef, es = ind.ema(close, fast), ind.ema(close, slow)
    entries = (ef > es) & (ef.shift(1) <= es.shift(1))
    exits = (ef < es) & (ef.shift(1) >= es.shift(1))
    return entries, exits


def _score(close: pd.Series, fast: int, slow: int) -> float:
    entries, exits = _ema_signals(close, fast, slow)
    res = run_backtest(close, entries, exits)
    rep = compute_report(res.equity_curve, res.trade_returns)
    # Prefer risk-adjusted return; penalize zero-trade params.
    return rep.sharpe if res.n_trades >= 2 else -1e9


DEFAULT_GRID = [(f, s) for f in (10, 20, 30) for s in (50, 100, 200) if f < s]


def walk_forward(
    close: pd.Series,
    train: int = 252,
    test: int = 63,
    grid: list[tuple[int, int]] | None = None,
) -> WalkForwardReport:
    grid = grid or DEFAULT_GRID
    close = close.dropna().reset_index(drop=True)
    n = len(close)

    windows: list[WindowResult] = []
    oos_equity: list[float] = [1.0]
    oos_trades_all: list[float] = []

    for tr, te in walk_forward_splits(n, train, test):
        train_close = close.iloc[tr]
        best = max(grid, key=lambda p: _score(train_close, *p))

        test_close = close.iloc[te]
        entries, exits = _ema_signals(test_close, *best)
        res = run_backtest(test_close, entries, exits, initial=1.0)
        seg = res.equity_curve or [1.0]
        # Compound the OOS segment onto the running OOS curve.
        base = oos_equity[-1]
        seg_norm = [base * (v / seg[0]) for v in seg] if seg[0] else [base]
        oos_equity.extend(seg_norm)
        oos_trades_all.extend(res.trade_returns)

        windows.append(WindowResult(
            train=(tr.start, tr.stop), test=(te.start, te.stop), chosen_params=best,
            oos_return=(seg_norm[-1] / base - 1) if base else 0.0, oos_trades=res.n_trades,
        ))

    report = compute_report(oos_equity, oos_trades_all)
    mc = monte_carlo(oos_trades_all, n_sims=1000) if oos_trades_all else {"n_sims": 0}
    return WalkForwardReport(windows, oos_equity, report, mc, grid)
