"""Leave-one-out layer attribution — which layer helps, which hurts.

Method: run the FULL stack as the reference, then disable ONE layer at a time and
re-measure on the same data. The delta tells you that layer's marginal value:

  * removing it HURTS  (delta < 0)  -> the layer is BENEFICIAL  (keep it)
  * removing it HELPS  (delta > 0)  -> the layer is HARMFUL      (consider off)
  * removing it ~0                  -> NEUTRAL (or insurance that doesn't bind here)

We score on a blend of profit factor, return and drawdown so a layer that trades
the raw return for much better risk-adjusted quality is credited correctly.

Honest by construction: it reports sample size and flags low-confidence verdicts.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from app.agents import build_agents_from_settings
from app.core.config import Settings
from app.orchestration.session import PaperTradingSession

# Each layer: (label, settings mutation to DISABLE it)
_AGENT_LAYERS = ["smc", "volume_profile", "macro", "news", "social", "ml"]
_DECISION_LAYERS = {
    "structure_stops": lambda s: setattr(s.strategy, "structure_stops", False),
    "smart_exits": lambda s: setattr(s.exits, "enabled", False),
    "cost_filter": lambda s: setattr(s.execution, "cost_aware", False),
    "portfolio": lambda s: setattr(s.portfolio, "enabled", False),
}


@dataclass
class LayerResult:
    layer: str
    delta_return: float       # full - without (positive => layer beneficial)
    delta_pf: float
    delta_win: float
    delta_maxdd: float        # positive => layer reduces drawdown (good)
    trades_without: int
    verdict: str              # BENEFICIAL | NEUTRAL | HARMFUL | INSURANCE
    note: str


@dataclass
class AttributionReport:
    full_return: float
    full_pf: float
    full_win: float
    full_maxdd: float
    full_trades: int
    layers: list[LayerResult]
    min_trades: int


def _metrics(settings: Settings, history: dict) -> tuple:
    import tempfile
    s = copy.deepcopy(settings)
    d = tempfile.mkdtemp(prefix="attr_")
    s.learning.store_path = f"{d}/kb.json"      # isolate learning (no leakage)
    s.learning.journal_path = f"{d}/j.jsonl"
    sess = PaperTradingSession(s, agents=build_agents_from_settings(s))
    sess.history = copy.deepcopy(history)
    sess.data_sources = {k: "data" for k in history}
    res = sess.run(warmup=min(230, max(120, len(next(iter(history.values()))) - 90)))
    r = res.report
    wins = sum(1 for t in res.trades if t.pnl > 0)
    win = (wins / len(res.trades)) if res.trades else 0.0
    return r.total_return, r.profit_factor, win, r.max_drawdown, len(res.trades)


def _verdict(dr: float, dpf: float, ddd: float, n_without: int, min_trades: int) -> tuple[str, str]:
    if n_without < min_trades:
        return "LOW_DATA", "too few trades to judge — gather more"
    # Composite: weight risk-adjusted quality (PF, drawdown) with return.
    score = dr + 0.02 * dpf + ddd  # ddd>0 means layer cut drawdown
    if abs(dr) < 0.002 and abs(dpf) < 0.1 and abs(ddd) < 0.002:
        return "NEUTRAL", "no measurable effect here (may be insurance)"
    if score > 0.003:
        return "BENEFICIAL", "removing it hurts -> keep"
    if score < -0.003:
        return "HARMFUL", "removing it helps -> consider disabling"
    return "NEUTRAL", "marginal effect"


def run_layer_attribution(settings: Settings, history: dict, min_trades: int = 15) -> AttributionReport:
    """Run the full stack, then leave-one-out for each layer."""
    settings = copy.deepcopy(settings).sync_layer_flags()
    full = _metrics(settings, history)
    f_ret, f_pf, f_win, f_dd, f_n = full

    results: list[LayerResult] = []

    def measure(label: str, mutate):
        s = copy.deepcopy(settings)
        mutate(s)
        ret, pf, win, dd, n = _metrics(s, history)
        dr = f_ret - ret           # full minus without
        dpf = f_pf - pf
        dwin = f_win - win
        ddd = dd - f_dd            # without minus full; >0 => full had lower DD (layer good)
        verdict, note = _verdict(dr, dpf, ddd, n, min_trades)
        results.append(LayerResult(label, dr, dpf, dwin, ddd, n, verdict, note))

    for name in _AGENT_LAYERS:
        if getattr(settings.layers, name):
            measure(name, lambda s, nm=name: setattr(s.layers, nm, False))
    for name, mut in _DECISION_LAYERS.items():
        if getattr(settings.layers, name, True):
            measure(name, mut)

    # Rank: most harmful first (so the founder sees what to cut), then beneficial.
    results.sort(key=lambda r: -(r.delta_return + r.delta_maxdd))
    return AttributionReport(f_ret, f_pf, f_win, f_dd, f_n, results, min_trades)
