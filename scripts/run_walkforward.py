#!/usr/bin/env python3
"""Walk-forward out-of-sample analysis (robustness check).

    python scripts/run_walkforward.py
    python scripts/run_walkforward.py --source crypto --symbol BTC/USDT
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backtesting.walk_forward import walk_forward  # noqa: E402
from app.data.market_data import SyntheticConfig, synthetic_ohlcv  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="synthetic", choices=["synthetic", "crypto", "equities"])
    ap.add_argument("--symbol", default="DEMO")
    ap.add_argument("--bars", type=int, default=1200)
    ap.add_argument("--train", type=int, default=252)
    ap.add_argument("--test", type=int, default=63)
    ap.add_argument("--pipeline", action="store_true",
                    help="walk-forward the FULL decision pipeline (not just EMA-cross)")
    args = ap.parse_args()

    if args.pipeline:
        from app.core.config import load_config
        from app.backtesting.pipeline_walkforward import run_pipeline_walk_forward
        symbols = [f"SYM{i}" for i in range(6)]
        wf = run_pipeline_walk_forward(
            load_config(), symbols, bars=max(args.bars, 600), train=args.train, test=args.test,
            param_name="min_rr", grid=[2.0, 2.5, 3.0],
        )
        print(f"Full-pipeline walk-forward OOS | {len(wf.windows)} windows | param={wf.param_name}")
        print("=" * 64)
        for w in wf.windows:
            print(f"  test[{w.test[0]:4d}:{w.test[1]:4d}] min_rr={w.param} -> "
                  f"OOS {w.oos_return:+.2%} (Sharpe {w.oos_sharpe:.2f}, {w.oos_trades} trades)")
        r = wf.oos_report
        print("=" * 64)
        print(f"OOS total return : {r.total_return:+.2%}")
        print(f"OOS Sharpe       : {r.sharpe:.2f}")
        print(f"OOS max drawdown : {r.max_drawdown:.2%}")
        print(f"OOS profit factor: {r.profit_factor:.2f}  | win rate {r.win_rate:.0%} | {r.n_trades} trades")
        print("\nNote: each test window is traded by a fresh session on unseen data.")
        return

    if args.source == "synthetic":
        df = synthetic_ohlcv(args.symbol, SyntheticConfig(bars=args.bars, drift=0.0005, volatility=0.014))
    else:
        from app.data.providers import make_provider
        df = make_provider(args.source).get_ohlcv(args.symbol, "1D", args.bars)

    wf = walk_forward(df["close"], train=args.train, test=args.test)
    r = wf.oos_report

    print(f"Walk-forward OOS | {args.symbol} | {len(wf.windows)} windows "
          f"(train={args.train}, test={args.test})")
    print("=" * 60)
    for w in wf.windows:
        print(f"  test[{w.test[0]:4d}:{w.test[1]:4d}] params EMA{w.chosen_params[0]}/{w.chosen_params[1]} "
              f"-> OOS {w.oos_return:+.2%} ({w.oos_trades} trades)")
    print("=" * 60)
    print(f"OOS total return  : {r.total_return:+.2%}")
    print(f"OOS Sharpe        : {r.sharpe:.2f}")
    print(f"OOS max drawdown  : {r.max_drawdown:.2%}")
    print(f"OOS profit factor : {r.profit_factor:.2f}")
    print(f"Param stability   : {wf.selection_stability:.0%} (windows agreeing on the top param set)")
    if wf.monte_carlo.get("n_sims"):
        mc = wf.monte_carlo
        print(f"Monte Carlo OOS   : median {mc['terminal_median']:.2f}x, "
              f"p05 {mc.get('terminal_p05', 0):.2f}x, maxDD p95 {mc['max_dd_p95']:.2%}")
    print("\nNote: OOS results are evaluated on data never used to pick parameters.")


if __name__ == "__main__":
    main()
