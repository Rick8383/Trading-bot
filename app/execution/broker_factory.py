"""Broker factory — safe by default.

Returns the in-process PaperBroker unless the operator has BOTH:
  1. set LIVE_TRADING_UNLOCK=I_UNDERSTAND_THE_RISK, and
  2. provided the relevant API keys.

Even then, the live venues are *paper/testnet* (fake money). There is no path in
this codebase that risks real capital without changing the live endpoints by
hand — a deliberate, multi-step barrier.
"""

from __future__ import annotations

import os

from app.core.config import Settings
from app.core.logging import get_logger

_log = get_logger("broker")


def make_broker(settings: Settings, venue: str = "auto"):
    """Build the execution broker for the requested venue.

    venue: "paper" (default in-process sim) | "alpaca" | "binance" | "auto".
    Falls back to the in-process PaperBroker whenever the unlock or keys are
    missing, logging the reason.
    """
    from app.execution.paper_broker import PaperBroker

    paper = PaperBroker(
        cash=settings.capital.initial,
        slippage_bps=settings.execution.slippage_bps,
        commission_bps=settings.execution.commission_bps,
        max_leverage=settings.risk.default_leverage,
    )

    if venue == "paper":
        return paper

    if not settings.live_unlocked:
        _log_warn("live venue requested but LIVE_TRADING_UNLOCK not set -> using in-process paper broker")
        return paper

    if venue in ("alpaca", "auto"):
        key, secret = os.getenv("ALPACA_KEY"), os.getenv("ALPACA_SECRET")
        if key and secret:
            from app.execution.live_broker import AlpacaPaperBroker

            _log_warn("using Alpaca PAPER broker (fake money)")
            return AlpacaPaperBroker(key, secret, unlocked=True)
        if venue == "alpaca":
            _log_warn("ALPACA_KEY/SECRET missing -> using in-process paper broker")
            return paper

    if venue in ("binance", "auto"):
        key, secret = os.getenv("BINANCE_KEY"), os.getenv("BINANCE_SECRET")
        if key and secret:
            from app.execution.live_broker import CcxtTestnetBroker

            _log_warn("using Binance TESTNET broker (fake money)")
            return CcxtTestnetBroker("binance", key, secret, unlocked=True)
        if venue == "binance":
            _log_warn("BINANCE_KEY/SECRET missing -> using in-process paper broker")
            return paper

    return paper


def _log_warn(msg: str) -> None:
    if hasattr(_log, "warning"):
        _log.warning("broker_factory", detail=msg)
