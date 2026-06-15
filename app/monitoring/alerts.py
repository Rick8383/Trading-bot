"""Alerting — pluggable sinks (log by default; Telegram/email are opt-in stubs).

Kept dependency-free so the core always has a working alerter. Real Telegram /
email transport is wired in once credentials exist; until then alerts go to the
structured log, which is itself auditable.
"""

from __future__ import annotations

from app.core.logging import get_logger

_log = get_logger("alerts")


class AlertManager:
    def __init__(self, telegram_enabled: bool = False, email_enabled: bool = False):
        self.telegram_enabled = telegram_enabled
        self.email_enabled = email_enabled
        self.sent: list[tuple[str, str]] = []

    def send(self, level: str, message: str, **context) -> None:
        self.sent.append((level, message))
        _log.info("alert", level=level, message=message, **context) if hasattr(_log, "info") else None
        # Telegram/email transport intentionally omitted until creds are set.

    def critical(self, message: str, **ctx) -> None:
        self.send("CRITICAL", message, **ctx)

    def warning(self, message: str, **ctx) -> None:
        self.send("WARNING", message, **ctx)

    def info(self, message: str, **ctx) -> None:
        self.send("INFO", message, **ctx)
