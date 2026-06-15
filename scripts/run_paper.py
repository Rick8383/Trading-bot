#!/usr/bin/env python3
"""Run a paper-trading session on fictional capital and print the results.

    python scripts/run_paper.py                       # offline mixed-regime demo
    python scripts/run_paper.py --source crypto       # real crypto candles (ccxt)
    python scripts/run_paper.py --source equities     # real equities/ETF (yfinance)
    python scripts/run_paper.py --source auto --symbols BTC/USDT ETH/USDT SPY QQQ
    python scripts/run_paper.py --db data_store/trading.db   # persist to SQLite

This is the founder's primary test loop: trade fictional money, watch the bot
make risk-first decisions, and — crucially — watch it learn from every closed
trade (lessons + improvement proposals are printed at the end). Learning, the
journal and the knowledge base persist across runs, so the bot gets sharper the
more you run it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_config  # noqa: E402
from app.orchestration.session import PaperTradingSession  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Paper-trading session")
    ap.add_argument("--source", default="synthetic",
                    choices=["synthetic", "crypto", "equities", "auto"],
                    help="data source (default: offline synthetic mixed regimes)")
    ap.add_argument("--symbols", nargs="*", default=None, help="override the symbol list")
    ap.add_argument("--exchange", default="binance", help="ccxt exchange for crypto")
    ap.add_argument("--bars", type=int, default=400)
    ap.add_argument("--warmup", type=int, default=230)
    ap.add_argument("--db", default=None, help="SQLite path for durable persistence")
    ap.add_argument("--report", default="reports/paper_report.html",
                    help="HTML report output path (set empty to skip)")
    args = ap.parse_args()

    settings = load_config()
    store = None
    if args.db:
        from app.db.store import SQLiteStore
        store = SQLiteStore(args.db)

    session = PaperTradingSession(settings, store=store)

    if args.source == "synthetic":
        symbols = args.symbols or [f"SYM{i}" for i in range(8)]
        session.load_synthetic_mixed(symbols, bars=args.bars)
    else:
        from app.data.providers import make_provider
        provider = make_provider(args.source, exchange=args.exchange)
        if args.symbols:
            symbols = args.symbols
        elif args.source == "crypto":
            symbols = settings.universe.crypto
        elif args.source == "equities":
            symbols = settings.universe.etfs + settings.universe.equities
        else:
            symbols = settings.universe.crypto[:4] + settings.universe.etfs[:4]
        session.load_from_provider(provider, symbols, bars=max(args.bars, 500))

    print(f"Paper trading {len(session.history)} symbols | source={args.source} | "
          f"initial ${settings.capital.initial:,.0f}")
    if session.data_sources:
        from collections import Counter
        srcs = Counter(session.data_sources.values())
        print(f"Data origin: {dict(srcs)}")
    print(f"Risk/trade={settings.risk.risk_per_trade:.2%}  min_RR={settings.risk.min_rr}  "
          f"max_DD={settings.risk.max_drawdown:.0%}\n")

    if not session.history:
        print("No symbols loaded — aborting.")
        return

    result = session.run(warmup=min(args.warmup, args.bars - 60))

    r = result.report
    print("=" * 60)
    print("PERFORMANCE (paper)")
    print("=" * 60)
    print(f"Decisions evaluated : {result.decisions}")
    print(f"Trades executed     : {result.executed}")
    print(f"Closed trades       : {r.n_trades}")
    print(f"Total return        : {r.total_return:+.2%}")
    print(f"CAGR (annualized)   : {r.cagr:+.2%}")
    print(f"Sharpe              : {r.sharpe:.2f}")
    print(f"Sortino             : {r.sortino:.2f}")
    print(f"Max drawdown        : {r.max_drawdown:.2%}")
    print(f"Calmar              : {r.calmar:.2f}")
    print(f"Profit factor       : {r.profit_factor:.2f}")
    print(f"Win rate            : {r.win_rate:.0%}")
    print(f"Kill switch tripped : {result.kill_switched}")

    print("\n" + "=" * 60)
    print(f"LESSONS LEARNED ({len(result.lessons)})  — the bot's growing memory")
    print("=" * 60)
    for lesson in result.lessons[:10]:
        print(f"  • {lesson.key}: {lesson.losses}/{lesson.samples} losses, "
              f"exp {lesson.expectancy:+.2%} -> penalty {lesson.penalty(session.kb.min_samples):.1f} pts")
    if not result.lessons:
        print("  (no confirmed loss-patterns yet — run more / more symbols)")

    print("\n" + "=" * 60)
    print(f"IMPROVEMENT PROPOSALS ({len(result.proposals)})  — advisory, never auto-applied")
    print("=" * 60)
    for p in result.proposals[:8]:
        print(f"  {p}")
    if not result.proposals:
        print("  (nothing actionable yet)")

    if store:
        print(f"\nPersisted to {args.db}: "
              f"{store.count('decisions')} decisions, {store.count('trades')} trades, "
              f"{store.count('lessons')} lessons, {store.count('metrics')} metric snapshots.")

    if args.report:
        from collections import Counter

        from app.monitoring.report import write_report
        path = write_report(
            args.report, title="Paper Trading Report",
            report=r, equity_curve=result.equity_curve, trades=result.trades,
            lessons=result.lessons, proposals=result.proposals,
            data_origin=dict(Counter(session.data_sources.values())),
            initial_capital=settings.capital.initial, min_samples=session.kb.min_samples,
        )
        print(f"\nHTML report written to {path}")


if __name__ == "__main__":
    main()
