"""Walk-forward analysis of the FULL decision pipeline (not just EMA-cross).

For each rolling split we (optionally) select one parameter on the train window,
then run a *fresh* paper session on the test window only — so every result is
strictly out-of-sample and windows don't leak into each other. This validates
the whole system (agents -> CIO -> risk veto -> structure stops -> smart exits)
the way it will actually trade, which is the real robustness question.

Kept lightweight: fresh sessions, no persistence, small default grids.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from app.backtesting.engine import walk_forward_splits
from app.core.config import Settings
from app.data.market_data import SyntheticConfig, synthetic_ohlcv
from app.monitoring.metrics import compute_report
from app.orchestration.session import PaperTradingSession


@dataclass
class PipelineWindow:
    train: tuple[int, int]
    test: tuple[int, int]
    param: float | None
    oos_return: float
    oos_trades: int
    oos_sharpe: float


@dataclass
class PipelineWFReport:
    windows: list[PipelineWindow]
    oos_trade_returns: list[float]
    oos_report: object
    param_name: str | None = None
    grid: list[float] = field(default_factory=list)


def _mixed_history(symbols: list[str], bars: int) -> dict:
    drifts = [0.004, -0.004, 0.0004, 0.005, -0.003, 0.0]
    vols = [0.012, 0.018, 0.02, 0.013, 0.022, 0.02]
    hist = {}
    for i, sym in enumerate(symbols):
        cfg = SyntheticConfig(bars=bars, drift=drifts[i % len(drifts)],
                              volatility=vols[i % len(vols)], seed=11 + i)
        hist[sym] = synthetic_ohlcv(sym, cfg)
    return hist


def _apply_param(settings: Settings, name: str, value: float) -> Settings:
    s = settings.model_copy(deep=True)
    if name == "min_rr":
        s.risk.min_rr = value
    elif name == "conviction_floor":
        s.conviction.flat_below = value
    elif name == "atr_stop_multiplier":
        s.strategy.atr_stop_multiplier = value
    return s


def _run_window(settings: Settings, history: dict, warmup: int, end: int):
    sess = PaperTradingSession(settings)
    sess.history = copy.deepcopy(history)
    sess.data_sources = {k: "synthetic" for k in history}
    return sess.run(warmup=warmup, end=end)


def run_pipeline_walk_forward(
    settings: Settings,
    symbols: list[str],
    bars: int = 600,
    train: int = 200,
    test: int = 100,
    warmup: int = 120,
    param_name: str | None = None,
    grid: list[float] | None = None,
) -> PipelineWFReport:
    history = _mixed_history(symbols, bars)
    windows: list[PipelineWindow] = []
    all_oos: list[float] = []

    for tr, te in walk_forward_splits(bars, train, test):
        if tr.start < warmup:
            continue  # need lead-in for indicators before the train window

        chosen: float | None = None
        used = settings
        if param_name and grid:
            # Select the parameter that maximizes train-window Sharpe.
            best_score, best = -1e9, grid[0]
            for v in grid:
                res = _run_window(_apply_param(settings, param_name, v), history, tr.start, tr.stop)
                score = res.report.sharpe if res.report.n_trades >= 2 else -1e9
                if score > best_score:
                    best_score, best = score, v
            chosen, used = best, _apply_param(settings, param_name, best)

        res = _run_window(used, history, te.start, te.stop)
        all_oos.extend(res.trade_returns)
        windows.append(PipelineWindow(
            train=(tr.start, tr.stop), test=(te.start, te.stop), param=chosen,
            oos_return=res.report.total_return, oos_trades=res.report.n_trades,
            oos_sharpe=res.report.sharpe,
        ))

    agg = compute_report([100_000.0] + [100_000.0 * (1 + r) for r in _cumulative(all_oos)], all_oos)
    return PipelineWFReport(windows, all_oos, agg, param_name, grid or [])


def _cumulative(returns: list[float]) -> list[float]:
    out, cum = [], 1.0
    for r in returns:
        cum *= (1 + r)
        out.append(cum - 1)
    return out
