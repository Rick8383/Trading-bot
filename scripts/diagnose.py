#!/usr/bin/env python3
"""Diagnose a live/paper run from the durable store — the honest picture.

    python scripts/diagnose.py --db data_store/trading.db

Turns "I'm down $X" into exactly what the bot did and why: P&L in perspective,
trade stats, cost drag, why it stayed flat, and the lessons it has learned.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_config  # noqa: E402


def _q(conn, sql, params=()):
    cur = conn.execute(sql, params)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data_store/trading.db")
    args = ap.parse_args()

    if not Path(args.db).exists():
        print(f"No database at {args.db}. Run with --db pointing at your live DB.")
        return

    initial = load_config().capital.initial
    conn = sqlite3.connect(args.db)

    def count(t):
        try:
            return conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except sqlite3.OperationalError:
            return 0

    n_dec, n_tr = count("decisions"), count("trades")
    metric = _q(conn, "SELECT * FROM metrics ORDER BY id DESC LIMIT 1")
    equity = metric[0]["equity"] if metric else initial
    pnl = equity - initial

    print("=" * 64)
    print("DIAGNOSTIC — what the bot actually did")
    print("=" * 64)
    print(f"Equity            : ${equity:,.2f}   (start ${initial:,.0f})")
    print(f"P&L               : {pnl:+,.2f}  ({pnl/initial:+.3%})")
    if metric:
        m = metric[0]
        print(f"Drawdown          : {m['drawdown']:.2%}   Sharpe {m.get('sharpe',0):.2f}  "
              f"PF {m.get('profit_factor',0):.2f}  win {m.get('win_rate',0):.0%}")
    print(f"Decisions analysed: {n_dec:,}")
    print(f"Trades closed     : {n_tr}")

    # --- trades breakdown ---
    trades = _q(conn, "SELECT pnl, return_pct, reason FROM trades")
    if trades:
        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        gross_w = sum(t["pnl"] for t in wins)
        gross_l = -sum(t["pnl"] for t in losses)
        avg_w = gross_w / len(wins) if wins else 0
        avg_l = gross_l / len(losses) if losses else 0
        print("\n--- Closed trades ---")
        print(f"  Win rate        : {len(wins)}/{len(trades)} = {len(wins)/len(trades):.0%}")
        print(f"  Avg win / loss  : +{avg_w:,.2f} / -{avg_l:,.2f}")
        print(f"  Gross W / L     : +{gross_w:,.2f} / -{gross_l:,.2f}")
        print(f"  Profit factor   : {gross_w/gross_l:.2f}" if gross_l > 0 else "  Profit factor   : inf")
        by_reason = Counter(t["reason"] for t in trades)
        print(f"  Exit reasons    : {dict(by_reason)}")
        if avg_w and avg_l and avg_l >= avg_w:
            print("  ! Avg loss >= avg win: tighten exits / let winners run / raise min_edge_pct.")
    else:
        print("\n--- No closed trades yet ---")
        print("  The bot is analysing but hasn't found setups clearing all gates.")

    # --- actionable vs filled (catches entries that never executed) ---
    actionable = conn.execute(
        "SELECT COUNT(*) FROM decisions WHERE rejected=0 AND action!='FLAT'"
    ).fetchone()[0]
    if actionable:
        print(f"\nActionable decisions (bot wanted to trade): {actionable:,}")
        if actionable > n_tr * 3 + 5:
            print("  ! Far more actionable decisions than trades -> entries weren't")
            print("    executing. Usual cause: pullback limit orders expiring unfilled.")
            print("    Fix shipped: entries default to MARKET now (set entries.mode).")

    # --- why flat ---
    flat = _q(conn, "SELECT rejection_reason FROM decisions WHERE rejected=1")
    if flat:
        reasons = Counter((r["rejection_reason"] or "")[:55] for r in flat)
        print("\n--- Why the bot stayed flat (top) ---")
        for r, c in reasons.most_common(6):
            print(f"  {c:6d}  {r}")

    # --- lessons ---
    lessons = _q(conn, "SELECT key, samples, losses, pnl_sum FROM lessons ORDER BY samples DESC LIMIT 8")
    if lessons:
        print("\n--- Lessons learned (memory) ---")
        for l in lessons:
            exp = l["pnl_sum"] / l["samples"] if l["samples"] else 0
            print(f"  {l['key'][:30]:30s} {l['losses']}L/{l['samples']} exp {exp:+.2%}")

    # --- verdict / perspective ---
    print("\n" + "=" * 64)
    print("PERSPECTIVE")
    print("=" * 64)
    if n_tr < 30:
        print(f"  Only {n_tr} closed trades — far too few to judge anything. A strategy's")
        print("  edge needs dozens-to-hundreds of trades and weeks to show. A small")
        print(f"  {pnl/initial:+.2%} here is noise + costs, not a verdict.")
    elif pnl >= 0:
        print(f"  {n_tr} trades, slightly positive. Keep gathering data before scaling.")
    else:
        print(f"  {n_tr} trades, slightly negative. Check the cost drag above: if avg")
        print("  loss ~ fee size, you're over-trading -> use --risk medium or raise")
        print("  execution.min_edge_pct. Losing more by trading more is the trap.")
    print("  Capital preservation first: a near-flat curve while learning is success,")
    print("  not failure.")


if __name__ == "__main__":
    main()
