import pandas as pd

from app.backtesting.engine import monte_carlo, run_backtest, walk_forward_splits
from app.data import indicators as ind
from app.data.market_data import SyntheticConfig, synthetic_ohlcv
from app.monitoring.metrics import compute_report, max_drawdown, sharpe


def test_max_drawdown():
    assert max_drawdown([100, 120, 90, 110]) == (120 - 90) / 120


def test_sharpe_zero_on_flat():
    assert sharpe([0.0, 0.0, 0.0]) == 0.0


def test_backtest_runs_and_reports():
    df = synthetic_ohlcv("BT", SyntheticConfig(bars=400, drift=0.0008, volatility=0.012))
    close = df["close"]
    fast, slow = ind.ema(close, 10), ind.ema(close, 50)
    entries = (fast > slow) & (fast.shift(1) <= slow.shift(1))
    exits = (fast < slow) & (fast.shift(1) >= slow.shift(1))
    res = run_backtest(close, entries, exits)
    assert len(res.equity_curve) == len(close.dropna())
    report = compute_report(res.equity_curve, res.trade_returns)
    assert report.n_trades == res.n_trades
    assert report.max_drawdown >= 0


def test_monte_carlo_distribution():
    mc = monte_carlo([0.02, -0.01, 0.03, -0.02, 0.05], n_sims=500)
    assert mc["n_sims"] == 500
    assert mc["terminal_p05"] <= mc["terminal_median"] <= mc["terminal_p95"]


def test_walk_forward_splits():
    splits = list(walk_forward_splits(10, train=4, test=2))
    assert splits
    tr, te = splits[0]
    assert tr.stop == te.start
