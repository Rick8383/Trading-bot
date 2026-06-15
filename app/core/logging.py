"""Structured, audit-grade logging.

Every decision the bot makes must be explainable after the fact. We use
structlog so logs are machine-parseable JSON-ish key/value events. Falls back
to the stdlib logger if structlog is unavailable.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

try:  # structlog is preferred but not strictly required
    import structlog

    _HAS_STRUCTLOG = True
except Exception:  # pragma: no cover - exercised only without structlog
    _HAS_STRUCTLOG = False


_configured = False


def configure_logging(level: str = "INFO") -> None:
    global _configured
    if _configured:
        return
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    if _HAS_STRUCTLOG:
        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, level.upper(), logging.INFO)
            ),
            cache_logger_on_first_use=True,
        )
    _configured = True


def get_logger(name: str = "tradingbot") -> Any:
    configure_logging()
    if _HAS_STRUCTLOG:
        return structlog.get_logger(name)
    return logging.getLogger(name)
