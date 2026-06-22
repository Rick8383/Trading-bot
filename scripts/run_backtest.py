#!/usr/bin/env python3
"""Demonstrate the backtest engine + Monte Carlo robustness check.

    python scripts/run_backtest.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backtesting.engine import monte_carlo, run_backtest  # noqa: E402
from app.data import indicators as ind  # noqa: E402
from app.data.market_data import SyntheticConfig, synthetic_ohlcv  # noqa: E402
from app.monitoring.metrics import compute_report  # noqa: E402


def main() -> None:
    df = synthetic_ohlcv("DEMO", SyntheticConfig(bars=750, drift=0.0006, volatility=0.015))
    close = df["close"]
    ema_fast = ind.ema(close, 20)
    ema_slow = ind.ema(close, 100)

    entries = (ema_fast > ema_slow) & (ema_fast.shift(1) <= ema_slow.shift(1))
    exits = (ema_fast < ema_slow) & (ema_fast.shift(1) >= ema_slow.shift(1))

    res = run_backtest(close, entries, exits)
    report = compute_report(res.equity_curve, res.trade_returns)

    print("Backtest: EMA20/EMA100 crossover (long-only, costs included)")
    print(f"  Trades        : {res.n_trades}")
    print(f"  Total return  : {report.total_return:+.2%}")
    print(f"  Sharpe        : {report.sharpe:.2f}")
    print(f"  Max drawdown  : {report.max_drawdown:.2%}")
    print(f"  Profit factor : {report.profit_factor:.2f}")

    mc = monte_carlo(res.trade_returns, n_sims=2000)
    print("\nMonte Carlo (2000 bootstrap resamples of trade order):")
    print(f"  Terminal multiple median : {mc['terminal_median']:.2f}x")
    print(f"  Terminal p05 / p95       : {mc.get('terminal_p05', 0):.2f}x / {mc.get('terminal_p95', 0):.2f}x")
    print(f"  Max drawdown p95         : {mc['max_dd_p95']:.2%}")


if __name__ == "__main__":
    main()
