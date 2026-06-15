"""FastAPI app exposing health, config, decisions, and the kill switch.

Read-mostly: the dashboard observes the bot. The only mutating endpoint is the
manual kill switch — a human safety control, intentionally always available.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from app.core.config import get_settings
from app.monitoring.kill_switch import KillSwitch

app = FastAPI(title="Algo Trading Bot", version="0.1.0")
_kill = KillSwitch()


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
