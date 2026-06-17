#!/usr/bin/env python3
"""Run the real-time decision loop (paper by default, live-paper if unlocked).

    # Safe default: in-process paper broker on real candles, a few cycles
    python scripts/run_live.py --source crypto --cycles 3

    # Live-paper on Alpaca (fake money) — requires, in your environment:
    #   export LIVE_TRADING_UNLOCK=I_UNDERSTAND_THE_RISK
    #   export ALPACA_KEY=...  ALPACA_SECRET=...     (paper keys from alpaca.markets)
    python scripts/run_live.py --source equities --venue alpaca --interval 3600

    # Live-paper on Binance testnet (fake money) — requires:
    #   export LIVE_TRADING_UNLOCK=I_UNDERSTAND_THE_RISK
    #   export BINANCE_KEY=... BINANCE_SECRET=...    (testnet keys)
    python scripts/run_live.py --source crypto --venue binance --interval 900

Without the unlock token and keys, every venue safely falls back to the
in-process paper broker and says so.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import apply_risk_profile, load_config  # noqa: E402
from app.data.providers import make_provider  # noqa: E402
from app.db import make_store  # noqa: E402
from app.execution.broker_factory import make_broker  # noqa: E402
from app.scheduler.loop import RealtimeRunner  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="auto", choices=["synthetic", "crypto", "equities", "auto"])
    ap.add_argument("--venue", default="paper", choices=["paper", "alpaca", "binance", "auto"])
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--interval", type=int, default=3600, help="seconds between cycles (start loop)")
    ap.add_argument("--cycles", type=int, default=0, help="run N cycles then exit (0 = run forever)")
    ap.add_argument("--db", default="data_store/trading.db")
    ap.add_argument("--ml", action="store_true", help="include the ML proposer agent")
    ap.add_argument("--timeframe", default="1D",
                    help="primary trading timeframe: 1m,5m,15m,30m,1H,4H,1D (default 1D)")
    ap.add_argument("--context-tf", default="1W", dest="context_tf",
                    help="higher timeframe for context (e.g. 1H when trading 5m)")
    ap.add_argument("--risk", default="medium", choices=["low", "medium", "high"],
                    help="risk profile: sizing + concurrency (guardrails always on)")
    args = ap.parse_args()

    s = apply_risk_profile(load_config(), args.risk)
    provider = make_provider("synthetic" if args.source == "synthetic" else args.source)
    broker = make_broker(s, args.venue)
    # Default to the full top-20 crypto universe (or all ETFs+equities).
    if args.symbols:
        symbols = args.symbols
    elif args.source in ("crypto", "auto"):
        symbols = s.universe.crypto
    else:
        symbols = s.universe.etfs + s.universe.equities

    from app.agents import build_agents
    runner = RealtimeRunner(settings=s, provider=provider, broker=broker,
                            symbols=symbols, store=make_store(args.db),
                            agents=build_agents(include_ml=args.ml),
                            base_timeframe=args.timeframe, context_timeframe=args.context_tf)
    print(f"Live loop | source={args.source} | venue={args.venue} | broker={type(broker).__name__} "
          f"| symbols={len(symbols)} | tf={args.timeframe}/{args.context_tf} | risk={args.risk} "
          f"| risk/trade={s.risk.risk_per_trade:.1%} | live_unlocked={s.live_unlocked}")
    if args.interval < 30 and args.cycles == 0:
        print("  WARNING: intervals <30s risk API bans on free data; 30-60s is the realistic floor.")

    if args.cycles > 0:
        for i in range(args.cycles):
            decisions = runner.run_once()
            traded = sum(1 for d in decisions if not d.rejected and d.action.value != "FLAT")
            print(f"  cycle {i + 1}/{args.cycles}: {len(decisions)} decisions, {traded} actionable")
        print(f"Done. DB: {runner.store.count('decisions')} decisions, {runner.store.count('trades')} trades.")
    else:
        runner.start(interval_seconds=args.interval)


if __name__ == "__main__":
    main()
