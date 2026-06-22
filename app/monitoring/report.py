"""Self-contained HTML reporting.

Generates a single standalone HTML file with inline CSS and **server-rendered
SVG charts** — no external JS/CDN, so it opens offline and inside locked-down
environments. Shows equity curve, drawdown, KPI cards, recent trades, the
lessons the bot has learned, and improvement proposals.
"""

from __future__ import annotations

import html
from pathlib import Path

# ---------------------------------------------------------------- SVG helpers


def _scale(values, lo, hi, out_lo, out_hi):
    if hi == lo:
        return [(out_lo + out_hi) / 2 for _ in values]
    return [out_lo + (v - lo) / (hi - lo) * (out_hi - out_lo) for v in values]


def svg_area(values: list[float], width: int = 820, height: int = 220,
             stroke: str = "#2dd4bf", fill: str = "rgba(45,212,191,0.12)",
             pad: int = 28) -> str:
    """Render a filled line chart for a numeric series."""
    if not values:
        return '<svg class="chart"></svg>'
    lo, hi = min(values), max(values)
    n = len(values)
    xs = _scale(list(range(n)), 0, max(1, n - 1), pad, width - pad)
    ys = _scale(values, lo, hi, height - pad, pad)  # invert: high value -> top
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    area = f"{pad},{height - pad} " + pts + f" {width - pad},{height - pad}"
    # gridlines + min/max labels
    grid = ""
    for frac in (0.0, 0.5, 1.0):
        y = pad + frac * (height - 2 * pad)
        val = hi - frac * (hi - lo)
        grid += f'<line x1="{pad}" y1="{y:.1f}" x2="{width - pad}" y2="{y:.1f}" stroke="#1f2937" stroke-width="1"/>'
        grid += f'<text x="4" y="{y + 4:.1f}" fill="#6b7280" font-size="11">{val:,.0f}</text>'
    return (
        f'<svg class="chart" viewBox="0 0 {width} {height}" width="100%" preserveAspectRatio="none">'
        f"{grid}"
        f'<polygon points="{area}" fill="{fill}" stroke="none"/>'
        f'<polyline points="{pts}" fill="none" stroke="{stroke}" stroke-width="2"/>'
        f"</svg>"
    )


def _drawdown_series(equity: list[float]) -> list[float]:
    peak = float("-inf")
    out = []
    for v in equity:
        peak = max(peak, v)
        out.append(-100 * (peak - v) / peak if peak > 0 else 0.0)
    return out


# ---------------------------------------------------------------- HTML report

_CSS = """
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:#0b0f17;color:#e5e7eb;font:14px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:920px;margin:0 auto;padding:28px}
h1{font-size:22px;margin:0 0 4px} h2{font-size:15px;color:#9ca3af;margin:28px 0 10px;text-transform:uppercase;letter-spacing:.05em}
.motto{color:#6b7280;font-style:italic;margin-bottom:20px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px}
.card{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:14px}
.card .k{color:#6b7280;font-size:12px;text-transform:uppercase} .card .v{font-size:20px;font-weight:600;margin-top:4px}
.pos{color:#34d399}.neg{color:#f87171}
.chart{background:#0d1320;border:1px solid #1f2937;border-radius:10px;display:block}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid #1f2937}
th{color:#6b7280;font-weight:500;text-transform:uppercase;font-size:11px}
.tag{display:inline-block;background:#1f2937;border-radius:5px;padding:1px 7px;font-size:11px;color:#cbd5e1}
.foot{color:#4b5563;font-size:11px;margin-top:32px;border-top:1px solid #1f2937;padding-top:12px}
"""


def _card(label: str, value: str, cls: str = "") -> str:
    return f'<div class="card"><div class="k">{html.escape(label)}</div><div class="v {cls}">{html.escape(value)}</div></div>'


def _pn(x: float) -> str:
    return "pos" if x >= 0 else "neg"


def generate_html_report(
    *,
    title: str,
    report,
    equity_curve: list[float],
    trades: list,
    lessons: list,
    proposals: list,
    data_origin: dict | None = None,
    initial_capital: float = 0.0,
    min_samples: int = 8,
) -> str:
    r = report
    cards = "".join([
        _card("Total return", f"{r.total_return:+.2%}", _pn(r.total_return)),
        _card("CAGR", f"{r.cagr:+.2%}", _pn(r.cagr)),
        _card("Sharpe", f"{r.sharpe:.2f}"),
        _card("Sortino", f"{r.sortino:.2f}"),
        _card("Max drawdown", f"{r.max_drawdown:.2%}", "neg"),
        _card("Calmar", f"{r.calmar:.2f}"),
        _card("Profit factor", f"{r.profit_factor:.2f}"),
        _card("Win rate", f"{r.win_rate:.0%}"),
        _card("Closed trades", f"{r.n_trades}"),
    ])

    eq_chart = svg_area(equity_curve) if equity_curve else ""
    dd_chart = svg_area(_drawdown_series(equity_curve), stroke="#f87171",
                        fill="rgba(248,113,113,0.10)") if equity_curve else ""

    # Trades table (most recent 25).
    trows = ""
    for t in list(trades)[-25:][::-1]:
        pnl = getattr(t, "pnl", 0.0)
        ret = getattr(t, "return_pct", 0.0)
        action = getattr(getattr(t, "action", None), "value", getattr(t, "action", ""))
        trows += (
            f"<tr><td>{html.escape(str(getattr(t,'symbol','')))}</td>"
            f"<td>{html.escape(str(action))}</td>"
            f"<td>{getattr(t,'entry',0):.2f}</td><td>{getattr(t,'exit',0):.2f}</td>"
            f'<td class="{_pn(pnl)}">{pnl:+,.0f}</td>'
            f'<td class="{_pn(ret)}">{ret:+.2%}</td>'
            f"<td><span class='tag'>{html.escape(str(getattr(t,'reason','')))}</span></td></tr>"
        )
    trows = trows or '<tr><td colspan="7" style="color:#6b7280">No closed trades.</td></tr>'

    # Lessons table.
    lrows = ""
    for l in lessons[:15]:
        lrows += (
            f"<tr><td><span class='tag'>{html.escape(l.key)}</span></td>"
            f"<td>{l.losses}/{l.samples}</td>"
            f'<td class="{_pn(l.expectancy)}">{l.expectancy:+.2%}</td>'
            f"<td class='neg'>-{l.penalty(min_samples):.1f}</td></tr>"
        )
    lrows = lrows or '<tr><td colspan="4" style="color:#6b7280">No confirmed loss-patterns yet.</td></tr>'

    props = "".join(f"<li>{html.escape(str(p))}</li>" for p in proposals[:10]) \
        or '<li style="color:#6b7280">Nothing actionable yet.</li>'

    origin = ""
    if data_origin:
        origin = " · data: " + ", ".join(f"{k}×{v}" for k, v in data_origin.items())

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{_CSS}</style></head><body><div class="wrap">
<h1>{html.escape(title)}</h1>
<div class="motto">Preserve capital first. Grow second. Trade only with a measured edge.</div>
<div class="motto" style="color:#4b5563">Initial ${initial_capital:,.0f}{origin} · ⚠️ paper / no performance guarantee</div>
<h2>Key metrics</h2><div class="cards">{cards}</div>
<h2>Equity curve</h2>{eq_chart}
<h2>Drawdown (%)</h2>{dd_chart}
<h2>Recent trades</h2><table><tr><th>Symbol</th><th>Side</th><th>Entry</th><th>Exit</th><th>PnL</th><th>Return</th><th>Exit reason</th></tr>{trows}</table>
<h2>Lessons learned <span style="color:#4b5563;text-transform:none">— the bot's growing memory</span></h2>
<table><tr><th>Context</th><th>Losses</th><th>Expectancy</th><th>Conviction penalty</th></tr>{lrows}</table>
<h2>Improvement proposals <span style="color:#4b5563;text-transform:none">— advisory, never auto-applied</span></h2>
<ul>{props}</ul>
<div class="foot">Generated by algo-trading-bot · research/education only · not financial advice.</div>
</div></body></html>"""


def write_report(path: str | Path, **kwargs) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(generate_html_report(**kwargs), encoding="utf-8")
    return p
