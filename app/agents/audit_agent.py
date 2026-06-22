"""Audit agent — records every decision, score, and order. Append-only.

The spec's hard requirement: no unexplained decision. This agent serializes each
FinalDecision (including consulted agents, conviction, risk flags, and learned
penalties) to an append-only log for later review.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.models import FinalDecision


class AuditAgent:
    name = "Audit_AI"

    def __init__(self, path: str | Path = "data_store/audit.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.records: list[dict] = []

    def record_decision(self, decision: FinalDecision) -> None:
        entry = {
            "type": "decision",
            "logged_at": datetime.now(timezone.utc).isoformat(),
            **decision.audit_dict(),
        }
        self.records.append(entry)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")

    def record_event(self, event: str, **payload) -> None:
        entry = {"type": "event", "event": event,
                 "logged_at": datetime.now(timezone.utc).isoformat(), **payload}
        self.records.append(entry)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")
