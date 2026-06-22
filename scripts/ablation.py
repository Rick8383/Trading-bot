#!/usr/bin/env python3
"""Ablation study: quantify what each advanced layer adds to trade decisions.

Runs the SAME data through the pipeline while turning layers on one at a time
(cumulative) and measures the impact. This is how you *validate* whether an
advanced layer earns its place — not by intuition, by measurement.

    python scripts/ablation.py
    python scripts/ablation.py --source crypto --symbols BTC/USDT ETH/USDT ...

NOTE: on synthetic data absolute numbers are unrealistically rosy; read the
*direction and relative size* of each layer's contribution, then re-run on real
data (or via walk-forward) before trusting magnitudes.
"""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents import build_agents  # noqa: E402
from app.core.config import apply_risk_profile, load_config  # noqa: E402
from app.data.market_data import SyntheticConfig, synthetic_ohlcv  # noqa: E402
from app.orchestration.session import PaperTradingSession  # noqa: E402


def _mixed_history(symbols, bars):
    drifts = [0.004, -0.004, 0.0006, 0.005, -0.003, 0.0]
    vols = [0.02, 0.03, 0.025, 0.018, 0.035, 0.022]
    h = {}
    for i, sym in enumerate(symbols):
        h[sym] = synthetic_ohlcv(sym, SyntheticConfig(
            bars=bars, drift=drifts[i % len(drifts)], volatility=vols[i % len(vols)], seed=11 + i))
    return h


def _run(base_settings, history, roster, mut, tag=""):
    import tempfile
    s = copy.deepcopy(base_settings)
    d = tempfile.mkdtemp(prefix="abl_")
    s.learning.store_path = f"{d}/kb.json"      # isolate learning per step (no leak)
    s.learning.journal_path = f"{d}/j.jsonl"
    mut(s)
    sess = PaperTradingSession(s, agents=roster(s))
    sess.history = copy.deepcopy(history)
    sess.data_sources = {k: "synthetic" for k in history}
    res = sess.run(warmup=230)
    r = res.report
    wins = sum(1 for t in res.trades if t.pnl > 0)
    return {
        "trades": len(res.trades),
        "win": (wins / len(res.trades)) if res.trades else 0.0,
        "pf": r.profit_factor,
        "ret": r.total_return,
        "mdd": r.max_drawdown,
        "sharpe": r.sharpe,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", type=int, default=440)
    ap.add_argument("--symbols", nargs="*", default=[f"C{i}" for i in range(12)])
    ap.add_argument("--risk", default="aggressive")
    args = ap.parse_args()

    base = apply_risk_profile(load_config(), args.risk)
    base.learning.store_path = "/tmp/ablation_kb.json"
    base.learning.journal_path = "/tmp/ablation_j.jsonl"
    history = _mixed_history(args.symbols, args.bars)

    # Rosters
    core = lambda s: build_agents(include_smc=False, include_macro=False,
                                  include_volume_profile=False, include_ml=False)
    plus_smc = lambda s: build_agents(include_smc=True, include_macro=False,
                                      include_volume_profile=False, include_ml=False)
    plus_vp = lambda s: build_agents(include_smc=True, include_macro=False,
                                     include_volume_profile=True, include_ml=False)
    plus_macro = lambda s: build_agents(include_smc=True, include_macro=True,
                                        include_volume_profile=True, include_ml=False)
    full_ml = lambda s: build_agents(include_smc=True, include_macro=True,
                                     include_volume_profile=True, include_ml=True)

    def m_off(s):  # rawest baseline: ATR stops, no exits/cost/portfolio
        s.strategy.structure_stops = False
        s.exits.enabled = False
        s.execution.cost_aware = False
        s.portfolio.enabled = False

    def m_struct(s): m_off(s); s.strategy.structure_stops = True
    def m_exits(s): m_struct(s); s.exits.enabled = True
    def m_cost(s): m_exits(s); s.execution.cost_aware = True
    def m_port(s): m_cost(s); s.portfolio.enabled = True

    # Cumulative layers (each row adds one capability on top of the previous).
    steps = [
        ("0 Core agents + ATR stops", core, m_off),
        ("1 + structure-aware SL/TP", core, m_struct),
        ("2 + smart exits", core, m_exits),
        ("3 + edge-net-of-costs", core, m_cost),
        ("4 + portfolio (corr)", core, m_port),
        ("5 + SMC agent", plus_smc, m_port),
        ("6 + Volume Profile", plus_vp, m_port),
        ("7 + Macro agent", plus_macro, m_port),
        ("8 + ML (calibrated)", full_ml, m_port),
    ]

    print(f"Ablation | {len(args.symbols)} symbols | risk={args.risk} | bars={args.bars}")
    print("(synthetic data — read RELATIVE contributions, not absolute magnitudes)\n")
    hdr = f"{'layer':30s} {'trades':>7} {'win':>6} {'PF':>7} {'return':>9} {'maxDD':>7} {'Sharpe':>7}"
    print(hdr); print("-" * len(hdr))
    prev = None
    for name, roster, mut in steps:
        r = _run(base, history, roster, mut)
        delta = ""
        if prev is not None:
            d = r["ret"] - prev["ret"]
            delta = f"  Δret {d:+.2%}"
        print(f"{name:30s} {r['trades']:7d} {r['win']:6.0%} {r['pf']:7.2f} "
              f"{r['ret']:+9.2%} {r['mdd']:7.2%} {r['sharpe']:7.2f}{delta}")
        prev = r


if __name__ == "__main__":
    main()
