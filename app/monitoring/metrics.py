"""Performance metrics — the KPIs the CIO watches.

Pure functions over an equity curve and a list of trade returns. No external
deps so they run anywhere (tests, dashboard, reports).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class PerformanceReport:
    total_return: float
    cagr: float
    sharpe: float
    sortino: float
    max_drawdown: float
    calmar: float
    profit_factor: float
    win_rate: float
    avg_win: float
    avg_loss: float
    n_trades: int

    def as_dict(self) -> dict:
        return self.__dict__


def max_drawdown(equity: list[float]) -> float:
    peak = -math.inf
    mdd = 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, (peak - v) / peak)
    return mdd


def _annualized_return(equity: list[float], periods_per_year: int) -> float:
    if len(equity) < 2 or equity[0] <= 0:
        return 0.0
    total = equity[-1] / equity[0]
    years = (len(equity) - 1) / periods_per_year
    if years <= 0:
        return 0.0
    return total ** (1 / years) - 1


def _returns(equity: list[float]) -> list[float]:
    out = []
    for a, b in zip(equity[:-1], equity[1:]):
        if a > 0:
            out.append(b / a - 1)
    return out


def sharpe(returns: list[float], periods_per_year: int = 252, rf: float = 0.0) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns) - rf / periods_per_year
    var = sum((r - sum(returns) / len(returns)) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(var)
    if std == 0:
        return 0.0
    return mean / std * math.sqrt(periods_per_year)


def sortino(returns: list[float], periods_per_year: int = 252) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    downside = [r for r in returns if r < 0]
    if not downside:
        return float("inf") if mean > 0 else 0.0
    dd = math.sqrt(sum(r ** 2 for r in downside) / len(downside))
    if dd == 0:
        return 0.0
    return mean / dd * math.sqrt(periods_per_year)


def compute_report(
    equity: list[float], trade_returns: list[float], periods_per_year: int = 252
) -> PerformanceReport:
    rets = _returns(equity)
    mdd = max_drawdown(equity)
    cagr = _annualized_return(equity, periods_per_year)
    total = (equity[-1] / equity[0] - 1) if len(equity) >= 2 and equity[0] > 0 else 0.0

    wins = [r for r in trade_returns if r > 0]
    losses = [r for r in trade_returns if r < 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    pf = gross_win / gross_loss if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)

    return PerformanceReport(
        total_return=total,
        cagr=cagr,
        sharpe=sharpe(rets, periods_per_year),
        sortino=sortino(rets, periods_per_year),
        max_drawdown=mdd,
        calmar=(cagr / mdd) if mdd > 0 else 0.0,
        profit_factor=pf,
        win_rate=len(wins) / len(trade_returns) if trade_returns else 0.0,
        avg_win=sum(wins) / len(wins) if wins else 0.0,
        avg_loss=sum(losses) / len(losses) if losses else 0.0,
        n_trades=len(trade_returns),
    )
