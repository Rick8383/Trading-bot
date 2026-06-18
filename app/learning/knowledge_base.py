"""Knowledge base: aggregate trade outcomes per setup-context and convert
confirmed-bad contexts into conviction penalties.

A "lesson" is a context key with enough samples and demonstrably negative
expectancy. The penalty grows with how bad and how certain the lesson is, and
is capped per-lesson; the CIO caps the total. This is the durable memory that
makes the bot stop repeating mistakes.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.learning.postmortem import signature_for_record
from app.learning.trade_journal import TradeRecord

_PER_LESSON_CAP = 12.0  # max conviction points a single lesson can dock


@dataclass
class Lesson:
    key: str
    samples: int = 0
    wins: int = 0
    losses: int = 0
    pnl_sum: float = 0.0
    description: str = ""
    remedy: str = ""
    updated_at: str = ""

    @property
    def loss_rate(self) -> float:
        return self.losses / self.samples if self.samples else 0.0

    @property
    def expectancy(self) -> float:
        return self.pnl_sum / self.samples if self.samples else 0.0

    def is_confirmed_bad(self, min_samples: int) -> bool:
        return (
            self.samples >= min_samples
            and self.expectancy < 0
            and self.loss_rate > 0.5
        )

    def is_confirmed_good(self, min_samples: int) -> bool:
        return (
            self.samples >= min_samples
            and self.expectancy > 0
            and self.loss_rate < 0.5
        )

    def penalty(self, min_samples: int) -> float:
        """Conviction points to subtract when this context is present."""
        if not self.is_confirmed_bad(min_samples):
            return 0.0
        # Severity from loss rate excess; certainty bonus as samples grow.
        severity = (self.loss_rate - 0.5) * 24.0          # up to 12 at 100% loss
        certainty = min(1.0, self.samples / (min_samples * 3))
        return float(min(_PER_LESSON_CAP, severity * (0.6 + 0.4 * certainty)))

    def bonus(self, min_samples: int) -> float:
        """Conviction points to ADD for a context with proven positive edge.

        Symmetric to ``penalty``: lean into setups that have actually worked,
        but only once enough samples confirm it (no overfitting to one lucky
        high-vol trade). Capped like penalties.
        """
        if not self.is_confirmed_good(min_samples):
            return 0.0
        strength = (0.5 - self.loss_rate) * 24.0          # up to 12 at 0% loss
        certainty = min(1.0, self.samples / (min_samples * 3))
        return float(min(_PER_LESSON_CAP, strength * (0.6 + 0.4 * certainty)))


class KnowledgeBase:
    def __init__(self, path: str | Path, min_samples: int = 8):
        self.path = Path(path)
        self.min_samples = min_samples
        self.lessons: dict[str, Lesson] = {}
        self.load()

    # --- persistence ---------------------------------------------------
    def load(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.lessons = {k: Lesson(**v) for k, v in data.get("lessons", {}).items()}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"lessons": {k: asdict(v) for k, v in self.lessons.items()}}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # --- learning ------------------------------------------------------
    def record(self, rec: TradeRecord, descriptions: dict[str, str] | None = None) -> None:
        """Update lesson stats from one closed trade (win or loss)."""
        descriptions = descriptions or {}
        for key in signature_for_record(rec):
            lesson = self.lessons.setdefault(key, Lesson(key=key))
            lesson.samples += 1
            lesson.pnl_sum += rec.return_pct
            if rec.is_loss:
                lesson.losses += 1
            else:
                lesson.wins += 1
            if key in descriptions:
                lesson.description, lesson.remedy = descriptions[key]
            lesson.updated_at = datetime.now(timezone.utc).isoformat()

    def ingest(self, rec: TradeRecord, error_tags) -> None:
        """Convenience: fold post-mortem ErrorTags (descriptions/remedies) in."""
        desc = {t.key: (t.description, t.remedy) for t in error_tags}
        self.record(rec, desc)

    # --- inference (feeds the CIO) ------------------------------------
    def penalties(self, signature_keys: list[str]) -> dict[str, float]:
        """Conviction penalties for a prospective setup's context keys."""
        out: dict[str, float] = {}
        for key in signature_keys:
            lesson = self.lessons.get(key)
            if lesson:
                p = lesson.penalty(self.min_samples)
                if p > 0:
                    out[key] = round(p, 2)
        return out

    def bonuses(self, signature_keys: list[str]) -> dict[str, float]:
        """Conviction bonuses for context keys with a proven positive edge."""
        out: dict[str, float] = {}
        for key in signature_keys:
            lesson = self.lessons.get(key)
            if lesson:
                b = lesson.bonus(self.min_samples)
                if b > 0:
                    out[key] = round(b, 2)
        return out

    def active_lessons(self) -> list[Lesson]:
        return [l for l in self.lessons.values() if l.is_confirmed_bad(self.min_samples)]

    def winning_contexts(self) -> list[Lesson]:
        return [l for l in self.lessons.values() if l.is_confirmed_good(self.min_samples)]
