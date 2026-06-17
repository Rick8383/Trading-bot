"""Live HTML dashboard rendered from the durable store (served at /dashboard).

Reuses the report's inline CSS + server-side SVG so the page is self-contained
and auto-refreshes every 15s. Reads only — never mutates trading state.
"""

from __future__ import annotations

import html

from app.monitoring.report import _CSS, _pn, svg_area


def _card(label: str, value: str, cls: str = "") -> str:
    return (f'<div class="card"><div class="k">{html.escape(label)}</div>'
            f'<div class="v {cls}">{html.escape(value)}</div></div>')


def render_dashboard(store, kill, settings) -> str:
    latest = store.latest_metric() if store else None
    history = store.metrics_history() if store else []
    trades = store.recent_trades(20) if store else []
    lessons = store.lessons_list() if store else []
    decisions = store.recent_decisions(40) if store else []
    n_decisions = store.count("decisions") if store else 0

    equity = [m["equity"] for m in history] if history else []
    eq_chart = svg_area(equity) if equity else '<div class="card">No metric snapshots yet — run scripts/run_paper.py --db data_store/trading.db</div>'

    def f(key, fmt, default="—"):
        if not latest or latest.get(key) is None:
            return default
        return fmt.format(latest[key])

    cards = "".join([
        _card("Equity", f("equity", "${:,.0f}")),
        _card("Drawdown", f("drawdown", "{:.2%}"), "neg"),
        _card("Sharpe", f("sharpe", "{:.2f}")),
        _card("Sortino", f("sortino", "{:.2f}")),
        _card("Max DD", f("max_drawdown", "{:.2%}"), "neg"),
        _card("Profit factor", f("profit_factor", "{:.2f}")),
        _card("Win rate", f("win_rate", "{:.0%}")),
        _card("Trades", f("n_trades", "{:.0f}")),
    ])

    ks_cls, ks_txt = ("neg", f"ACTIVE — {kill.reason}") if kill.is_active else ("pos", "armed / inactive")
    kill_banner = f'<div class="card"><div class="k">Kill switch</div><div class="v {ks_cls}">{html.escape(ks_txt)}</div></div>'

    trows = ""
    for t in trades:
        pnl, ret = t.get("pnl", 0.0), t.get("return_pct", 0.0)
        trows += (f"<tr><td>{html.escape(str(t.get('symbol','')))}</td>"
                  f"<td>{html.escape(str(t.get('action','')))}</td>"
                  f'<td class="{_pn(pnl)}">{pnl:+,.0f}</td>'
                  f'<td class="{_pn(ret)}">{ret:+.2%}</td>'
                  f"<td><span class='tag'>{html.escape(str(t.get('reason','')))}</span></td></tr>")
    trows = trows or '<tr><td colspan="5" style="color:#6b7280">No trades yet.</td></tr>'

    # Analysis activity — shows the bot is working even when it stays flat.
    from collections import Counter
    flat_reasons = Counter(
        (d.get("rejection_reason") or "")[:60] for d in decisions if d.get("rejected")
    )
    actionable = sum(1 for d in decisions if not d.get("rejected") and d.get("action") != "FLAT")
    activity = (f'<div class="card"><div class="k">Decisions analysed (total)</div>'
                f'<div class="v">{n_decisions:,}</div></div>'
                f'<div class="card"><div class="k">Actionable (last 40)</div>'
                f'<div class="v">{actionable}</div></div>')
    rrows = ""
    for reason, cnt in flat_reasons.most_common(5):
        rrows += f"<tr><td>{html.escape(reason)}</td><td>{cnt}</td></tr>"
    rrows = rrows or '<tr><td colspan="2" style="color:#6b7280">No flat decisions recorded.</td></tr>'

    lrows = ""
    for l in lessons[:12]:
        exp = (l["pnl_sum"] / l["samples"]) if l.get("samples") else 0.0
        lrows += (f"<tr><td><span class='tag'>{html.escape(l['key'])}</span></td>"
                  f"<td>{l.get('losses',0)}/{l.get('samples',0)}</td>"
                  f'<td class="{_pn(exp)}">{exp:+.2%}</td></tr>')
    lrows = lrows or '<tr><td colspan="3" style="color:#6b7280">No lessons yet.</td></tr>'

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="15">
<title>Trading Bot — Live Dashboard</title><style>{_CSS}</style></head><body><div class="wrap">
<h1>Live Dashboard <span style="color:#4b5563;font-size:13px">· mode {html.escape(settings.mode)} · auto-refresh 15s</span></h1>
<div class="motto">Preserve capital first. Grow second. Trade only with a measured edge.</div>
<h2>Status</h2><div class="cards">{kill_banner}{cards}</div>
<h2>Analysis activity</h2><div class="cards">{activity}</div>
<table><tr><th>Why the bot stayed flat (top reasons)</th><th>Count</th></tr>{rrows}</table>
<h2>Equity curve</h2>{eq_chart}
<h2>Recent trades</h2><table><tr><th>Symbol</th><th>Side</th><th>PnL</th><th>Return</th><th>Reason</th></tr>{trows}</table>
<h2>Lessons learned</h2><table><tr><th>Context</th><th>Losses</th><th>Expectancy</th></tr>{lrows}</table>
<div class="foot">algo-trading-bot · paper / no performance guarantee · not financial advice.</div>
</div></body></html>"""
