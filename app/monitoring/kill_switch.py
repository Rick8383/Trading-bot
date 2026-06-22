"""Kill switch — a single, sticky, manually-resettable circuit breaker.

When engaged it blocks all new risk. Resetting is deliberately a manual action:
the system never silently re-arms itself after a serious event.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class KillSwitch:
    enabled: bool = False
    reason: str | None = None
    triggered_at: datetime | None = None
    history: list[dict] = field(default_factory=list)

    def trigger(self, reason: str) -> None:
        if not self.enabled:
            self.enabled = True
            self.reason = reason
            self.triggered_at = datetime.now(timezone.utc)
            self.history.append({"event": "trigger", "reason": reason, "at": self.triggered_at.isoformat()})

    def reset(self, operator: str = "manual") -> None:
        self.history.append({
            "event": "reset", "by": operator,
            "at": datetime.now(timezone.utc).isoformat(),
        })
        self.enabled = False
        self.reason = None
        self.triggered_at = None

    @property
    def is_active(self) -> bool:
        return self.enabled


def should_trigger(*, drawdown: float, daily_loss: float, max_dd: float, daily_limit: float) -> str | None:
    """Return a reason string if conditions warrant the kill switch, else None."""
    if drawdown >= max_dd:
        return f"max drawdown breached: {drawdown:.1%} >= {max_dd:.0%}"
    if daily_loss >= daily_limit * 2:  # severe single-day loss
        return f"severe daily loss: {daily_loss:.1%}"
    return None
