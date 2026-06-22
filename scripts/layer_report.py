#!/usr/bin/env python3
"""Daily per-layer contribution report — which layer helps, which hurts.

Leave-one-out attribution over the full stack on the same data, with a verdict
per layer (beneficial / neutral / harmful) and a recommendation. Writes a text
summary, a self-contained HTML report, and appends a dated JSON history so you
can watch each layer's value evolve over time.

    python scripts/layer_report.py                      # one-shot, synthetic
    python scripts/layer_report.py --source crypto      # on real cached candles
    python scripts/layer_report.py --loop-daily         # run once every 24h

Disable a layer the report flags as harmful by editing config.yaml `layers:`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.layer_attribution import run_layer_attribution  # noqa: E402
from app.core.config import apply_risk_profile, load_config  # noqa: E402
from app.data.market_data import SyntheticConfig, synthetic_ohlcv  # noqa: E402
from app.monitoring.report import _CSS  # noqa: E402

_VERDICT_EMOJI = {"BENEFICIAL": "🟢", "HARMFUL": "🔴", "NEUTRAL": "⚪", "LOW_DATA": "🟡"}


def _history(source: str, symbols: list[str], bars: int) -> dict:
    if source == "synthetic":
        drifts = [0.004, -0.004, 0.0006, 0.005, -0.003, 0.0]
        vols = [0.02, 0.03, 0.025, 0.018, 0.035, 0.022]
        return {s: synthetic_ohlcv(s, SyntheticConfig(bars=bars, drift=drifts[i % 6],
                volatility=vols[i % 6], seed=11 + i)) for i, s in enumerate(symbols)}
    from app.data.providers import make_provider
    prov = make_provider(source)
    out = {}
    for s in symbols:
        try:
            df = prov.get_ohlcv(s, "1D", bars)
            if len(df) >= 250:
                out[s] = df
        except Exception:  # noqa: BLE001
            continue
    return out


def _render_text(rep, source: str) -> str:
    lines = [
        f"LAYER ATTRIBUTION REPORT — {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC | source={source}",
        f"Full stack: return {rep.full_return:+.2%} | PF {rep.full_pf:.2f} | "
        f"win {rep.full_win:.0%} | maxDD {rep.full_maxdd:.2%} | {rep.full_trades} trades",
        "(positive Δ = the layer is beneficial; sample is small unless trades are many)",
        "-" * 78,
        f"{'layer':18s}{'verdict':12s}{'Δreturn':>9}{'ΔPF':>7}{'Δwin':>7}{'ΔmaxDD':>8}  note",
    ]
    for r in rep.layers:
        e = _VERDICT_EMOJI.get(r.verdict, "")
        lines.append(f"{r.layer:18s}{e+' '+r.verdict:12s}{r.delta_return:+9.2%}{r.delta_pf:+7.2f}"
                     f"{r.delta_win:+7.0%}{r.delta_maxdd:+8.2%}  {r.note}")
    harmful = [r.layer for r in rep.layers if r.verdict == "HARMFUL"]
    lines.append("-" * 78)
    if harmful:
        lines.append(f"RECOMMENDATION: consider disabling -> {', '.join(harmful)} "
                     "(set layers.<name>: false in config.yaml)")
    else:
        lines.append("RECOMMENDATION: no layer is clearly harmful on this data.")
    if rep.full_trades < rep.min_trades * 2:
        lines.append("⚠️  Small sample — treat as directional, re-run on more real data before acting.")
    return "\n".join(lines)


def _render_html(rep, source: str) -> str:
    rows = ""
    color = {"BENEFICIAL": "#34d399", "HARMFUL": "#f87171", "NEUTRAL": "#9ca3af", "LOW_DATA": "#fbbf24"}
    for r in rep.layers:
        c = color.get(r.verdict, "#9ca3af")
        rows += (f"<tr><td>{r.layer}</td><td style='color:{c}'>{r.verdict}</td>"
                 f"<td>{r.delta_return:+.2%}</td><td>{r.delta_pf:+.2f}</td>"
                 f"<td>{r.delta_win:+.0%}</td><td>{r.delta_maxdd:+.2%}</td>"
                 f"<td style='color:#6b7280'>{r.note}</td></tr>")
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Layer Report</title>
<style>{_CSS}</style></head><body><div class="wrap">
<h1>Layer attribution — {datetime.now(timezone.utc):%Y-%m-%d}</h1>
<div class="motto">Leave-one-out: positive Δ means the layer earns its place. source={source}</div>
<div class="cards">
<div class="card"><div class="k">Full return</div><div class="v">{rep.full_return:+.2%}</div></div>
<div class="card"><div class="k">Profit factor</div><div class="v">{rep.full_pf:.2f}</div></div>
<div class="card"><div class="k">Win rate</div><div class="v">{rep.full_win:.0%}</div></div>
<div class="card"><div class="k">Max DD</div><div class="v">{rep.full_maxdd:.2%}</div></div>
<div class="card"><div class="k">Trades</div><div class="v">{rep.full_trades}</div></div>
</div>
<h2>Per-layer contribution (Δ = full − without)</h2>
<table><tr><th>Layer</th><th>Verdict</th><th>Δreturn</th><th>ΔPF</th><th>Δwin</th><th>ΔmaxDD</th><th>Note</th></tr>
{rows}</table>
<div class="foot">Small samples are directional only. Disable a harmful layer via config.yaml layers:.</div>
</div></body></html>"""


def _append_history(rep, path: Path, source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"date": date.today().isoformat(), "source": source,
             "full": {"return": rep.full_return, "pf": rep.full_pf, "trades": rep.full_trades},
             "layers": {r.layer: {"verdict": r.verdict, "d_return": r.delta_return,
                                  "d_pf": r.delta_pf, "d_maxdd": r.delta_maxdd} for r in rep.layers}}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def run_once(args) -> None:
    s = apply_risk_profile(load_config(), args.risk)
    symbols = args.symbols or (s.universe.crypto[:8] if args.source != "synthetic"
                               else [f"C{i}" for i in range(8)])
    history = _history(args.source, symbols, args.bars)
    if not history:
        print("No data available — aborting."); return
    rep = run_layer_attribution(s, history, min_trades=args.min_trades)
    text = _render_text(rep, args.source)
    print(text)
    out = Path("reports")
    (out / "layer_report.txt").write_text(text, encoding="utf-8")
    (out / f"layer_report_{date.today().isoformat()}.html").write_text(
        _render_html(rep, args.source), encoding="utf-8")
    _append_history(rep, out / "layer_history.jsonl", args.source)
    print(f"\nWritten: reports/layer_report.txt + dated HTML + reports/layer_history.jsonl")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="synthetic", choices=["synthetic", "crypto", "equities", "auto"])
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--bars", type=int, default=360)
    ap.add_argument("--risk", default="aggressive")
    ap.add_argument("--min-trades", type=int, default=15, dest="min_trades")
    ap.add_argument("--loop-daily", action="store_true", help="run once every 24h")
    args = ap.parse_args()

    if args.loop_daily:
        while True:
            run_once(args)
            print("Next layer report in 24h...")
            time.sleep(24 * 3600)
    else:
        run_once(args)


if __name__ == "__main__":
    main()
