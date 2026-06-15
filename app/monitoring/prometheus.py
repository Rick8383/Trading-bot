"""Prometheus exposition — dependency-free text format.

Renders the latest snapshot from the durable store into the Prometheus text
exposition format so Grafana can scrape it via a Prometheus server. No
prometheus_client dependency required.
"""

from __future__ import annotations


def _line(name: str, value, help_text: str, gauge_type: str = "gauge") -> str:
    if value is None:
        value = 0
    return (f"# HELP {name} {help_text}\n"
            f"# TYPE {name} {gauge_type}\n"
            f"{name} {float(value)}\n")


def render_prometheus(store, kill) -> str:
    m = store.latest_metric() if store else None
    out = []
    out.append(_line("tradingbot_kill_switch_active", 1 if kill.is_active else 0,
                     "1 if the kill switch is engaged"))
    if m:
        out.append(_line("tradingbot_equity", m.get("equity"), "Current equity"))
        out.append(_line("tradingbot_drawdown", m.get("drawdown"), "Current drawdown fraction"))
        out.append(_line("tradingbot_sharpe", m.get("sharpe"), "Sharpe ratio"))
        out.append(_line("tradingbot_sortino", m.get("sortino"), "Sortino ratio"))
        out.append(_line("tradingbot_profit_factor", m.get("profit_factor"), "Profit factor"))
        out.append(_line("tradingbot_max_drawdown", m.get("max_drawdown"), "Max drawdown fraction"))
        out.append(_line("tradingbot_win_rate", m.get("win_rate"), "Win rate fraction"))
        out.append(_line("tradingbot_trades_total", m.get("n_trades"),
                         "Closed trades count", "counter"))
    if store:
        out.append(_line("tradingbot_decisions_total", store.count("decisions"),
                         "Decisions evaluated", "counter"))
        out.append(_line("tradingbot_lessons_total", store.count("lessons"),
                         "Learned lessons stored", "counter"))
    return "".join(out)
