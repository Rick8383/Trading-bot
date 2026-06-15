#!/usr/bin/env python3
"""Run a paper-trading session on fictional capital and print the results.

    python scripts/run_paper.py

This is the founder's primary test loop: trade fictional money, watch the bot
make risk-first decisions, and — crucially — watch it learn from every closed
trade (lessons + improvement proposals are printed at the end).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_config  # noqa: E402
from app.orchestration.session import PaperTradingSession  # noqa: E402


def main() -> None:
    settings = load_config()
    universe = settings.universe.all_symbols()[:12]
    print(f"Paper trading {len(universe)} symbols | initial ${settings.capital.initial:,.0f}")
    print(f"Risk/trade={settings.risk.risk_per_trade:.2%}  min_RR={settings.risk.min_rr}  "
          f"max_DD={settings.risk.max_drawdown:.0%}\n")

    session = PaperTradingSession(settings)
    session.load_synthetic(universe, bars=400)
    result = session.run(warmup=230)

    r = result.report
    print("=" * 60)
    print("PERFORMANCE (paper, synthetic data)")
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
        print("  (no confirmed loss-patterns yet — needs more samples)")

    print("\n" + "=" * 60)
    print(f"IMPROVEMENT PROPOSALS ({len(result.proposals)})  — advisory, never auto-applied")
    print("=" * 60)
    for p in result.proposals[:8]:
        print(f"  {p}")
    if not result.proposals:
        print("  (nothing actionable yet)")


if __name__ == "__main__":
    main()
