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

from app.core.config import load_config  # noqa: E402
from app.data.providers import make_provider  # noqa: E402
from app.db.store import SQLiteStore  # noqa: E402
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
    args = ap.parse_args()

    s = load_config()
    provider = make_provider("synthetic" if args.source == "synthetic" else args.source)
    broker = make_broker(s, args.venue)
    symbols = args.symbols or (s.universe.crypto[:5] if args.source in ("crypto", "auto") else s.universe.etfs)

    from app.agents import build_agents
    runner = RealtimeRunner(settings=s, provider=provider, broker=broker,
                            symbols=symbols, store=SQLiteStore(args.db),
                            agents=build_agents(include_ml=args.ml))
    print(f"Live loop | source={args.source} | venue={args.venue} | broker={type(broker).__name__} "
          f"| symbols={len(symbols)} | live_unlocked={s.live_unlocked}")

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
