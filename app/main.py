"""Entry point: ``uvicorn app.main:app`` serves the monitoring API.

The trading logic runs via the scripts (paper/backtest); this module just
exposes the FastAPI surface and a friendly root banner.
"""

from __future__ import annotations

from app.api.app import app

__all__ = ["app"]


@app.get("/")
def root() -> dict:
    return {
        "name": "algo-trading-bot",
        "mode": "paper",
        "motto": "Preserve capital first. Grow second. Trade only with a measured edge.",
        "docs": "/docs",
    }
