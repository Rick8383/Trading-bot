"""Rolling drawdown + daily-loss tracking.

Feeds the capital-preservation ladder and the kill switch. Keeps a running peak
of equity and derives the current drawdown from it.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DrawdownGuard:
    peak_equity: float
    start_of_day_equity: float
    current_equity: float = field(default=0.0)

    def __post_init__(self) -> None:
        if self.current_equity == 0.0:
            self.current_equity = self.peak_equity

    def update(self, equity: float) -> None:
        self.current_equity = equity
        self.peak_equity = max(self.peak_equity, equity)

    def roll_day(self) -> None:
        """Call at the start of each trading day."""
        self.start_of_day_equity = self.current_equity

    @property
    def drawdown(self) -> float:
        """Positive fraction below the running peak (0.07 == 7% under water)."""
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self.current_equity) / self.peak_equity)

    @property
    def daily_loss(self) -> float:
        """Positive fraction lost since start of day (0 if flat/up)."""
        if self.start_of_day_equity <= 0:
            return 0.0
        change = (self.current_equity - self.start_of_day_equity) / self.start_of_day_equity
        return max(0.0, -change)
