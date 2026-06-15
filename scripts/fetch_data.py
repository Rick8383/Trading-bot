#!/usr/bin/env python3
"""Pre-fetch and cache real market data so paper runs work fast / offline.

    python scripts/fetch_data.py --source crypto
    python scripts/fetch_data.py --source equities --symbols SPY QQQ AAPL

Run this on a machine with open network egress. Cached CSVs land in
data_store/cache/ and are reused automatically by run_paper.py.

NOTE: in a restricted cloud session, external market-data hosts must be on the
environment's egress allowlist (e.g. api.binance.com, query1/2.finance.yahoo.com)
or this will fall back to synthetic data and say so.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_config  # noqa: E402
from app.data.providers import make_provider  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="crypto", choices=["crypto", "equities", "auto"])
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--exchange", default="binance")
    ap.add_argument("--bars", type=int, default=750)
    args = ap.parse_args()

    s = load_config()
    provider = make_provider(args.source, exchange=args.exchange)
    if args.symbols:
        symbols = args.symbols
    elif args.source == "crypto":
        symbols = s.universe.crypto
    elif args.source == "equities":
        symbols = s.universe.etfs + s.universe.equities
    else:
        symbols = s.universe.crypto[:4] + s.universe.etfs[:4]

    for sym in symbols:
        try:
            df = provider.get_ohlcv(sym, "1D", args.bars)
            src = getattr(provider, "last_source", {}).get(sym, "live")
            last = df["close"].iloc[-1] if len(df) else float("nan")
            print(f"  {sym:12s} {len(df):4d} bars  source={src:18s} last={last:.4f}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {sym:12s} FAILED: {type(exc).__name__}: {str(exc)[:80]}")


if __name__ == "__main__":
    main()
