"""FastAPI app: health, config, kill switch, and a live monitoring dashboard.

Read-mostly: the dashboard observes the bot by reading the durable SQLite store
(the same DB the paper session writes to). The only mutating endpoints are the
manual kill switch — a human safety control, intentionally always available.

Point the dashboard at a DB with:  TRADING_DB=data_store/trading.db uvicorn ...
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from app.core.config import get_settings
from app.monitoring.kill_switch import KillSwitch

app = FastAPI(title="Algo Trading Bot", version="0.2.0")
_kill = KillSwitch()


def _store():
    """Lazily open the SQLite store if it exists; else None (empty dashboard)."""
    path = Path(os.getenv("TRADING_DB", "data_store/trading.db"))
    if not path.exists():
        return None
    from app.db.store import SQLiteStore

    return SQLiteStore(path)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/config")
def config() -> dict:
    s = get_settings()
    return {
        "mode": s.mode,
        "live_unlocked": s.live_unlocked,
        "risk_per_trade": s.risk.risk_per_trade,
        "max_drawdown": s.risk.max_drawdown,
        "min_rr": s.risk.min_rr,
        "max_positions": s.risk.max_positions,
        "universe": s.universe.all_symbols(),
    }


@app.get("/metrics")
def metrics() -> dict:
    st = _store()
    return {"latest": st.latest_metric() if st else None,
            "history": st.metrics_history() if st else []}


@app.get("/trades")
def trades(limit: int = 50) -> dict:
    st = _store()
    return {"trades": st.recent_trades(limit) if st else []}


@app.get("/decisions")
def decisions(limit: int = 50) -> dict:
    st = _store()
    return {"decisions": st.recent_decisions(limit) if st else []}


@app.get("/lessons")
def lessons() -> dict:
    st = _store()
    return {"lessons": st.lessons_list() if st else []}


@app.get("/kill-switch")
def kill_status() -> dict:
    return {"active": _kill.is_active, "reason": _kill.reason}


@app.post("/kill-switch/trigger")
def kill_trigger(reason: str = "manual operator action") -> dict:
    _kill.trigger(reason)
    return {"active": _kill.is_active, "reason": _kill.reason}


@app.post("/kill-switch/reset")
def kill_reset(operator: str = "operator") -> dict:
    if not _kill.is_active:
        raise HTTPException(status_code=400, detail="kill switch is not active")
    _kill.reset(operator)
    return {"active": _kill.is_active}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> str:
    """Live HTML dashboard rendered from the durable store."""
    from app.monitoring.dashboard import render_dashboard

    st = _store()
    return render_dashboard(st, kill=_kill, settings=get_settings())
