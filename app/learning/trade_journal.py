"""Durable, append-only journal of every closed trade with full context.

Append-only JSONL: each line is one immutable record. This is the raw material
the bot learns from and the auditor reviews. We never rewrite history.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class TradeRecord:
    """Decision context + realized outcome, joined for analysis."""

    symbol: str
    action: str
    entry: float
    exit: float
    stop_loss: float
    take_profit: float | None
    quantity: float
    pnl: float
    return_pct: float
    reason: str                         # stop_loss | take_profit | manual | ...
    # Decision-time context (what we believed when we entered):
    conviction: float = 0.0
    expected_value: float = 0.0
    reward_risk: float = 0.0
    win_probability: float = 0.5
    regime: str = "unknown"
    risk_flags: list[str] = field(default_factory=list)
    consulted_agents: list[str] = field(default_factory=list)
    # Post-mortem (filled by analysis):
    error_tags: list[str] = field(default_factory=list)
    opened_at: str = ""
    closed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def is_loss(self) -> bool:
        return self.pnl < 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)


class TradeJournal:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: TradeRecord) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(record.to_json() + "\n")

    def load(self) -> list[TradeRecord]:
        if not self.path.exists():
            return []
        out: list[TradeRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data: dict[str, Any] = json.loads(line)
            out.append(TradeRecord(**data))
        return out
