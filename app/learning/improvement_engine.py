"""Self-Improvement AI — proposes changes, never deploys them.

Per the spec's hard rule, this module can suggest new parameters or rules based
on aggregate evidence, but a human (the founder) must approve. It emits a
prioritized list of proposals with the statistical justification attached.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.learning.knowledge_base import KnowledgeBase
from app.learning.trade_journal import TradeRecord


@dataclass
class Proposal:
    title: str
    rationale: str
    suggested_change: str
    evidence_samples: int
    priority: float            # higher = more urgent

    def __str__(self) -> str:
        return f"[p{self.priority:.1f}] {self.title} — {self.suggested_change} ({self.evidence_samples} samples)"


def propose_improvements(kb: KnowledgeBase, journal: list[TradeRecord]) -> list[Proposal]:
    """Derive human-reviewable proposals from confirmed lessons + journal stats.

    NOTHING here is applied automatically. Output is advisory only.
    """
    proposals: list[Proposal] = []

    for lesson in kb.active_lessons():
        proposals.append(Proposal(
            title=f"Address recurring loss context '{lesson.key}'",
            rationale=(
                f"{lesson.losses}/{lesson.samples} losses, "
                f"avg return {lesson.expectancy:.2%} in this context."
            ),
            suggested_change=lesson.remedy or f"Add a filter / conviction penalty for '{lesson.key}'.",
            evidence_samples=lesson.samples,
            priority=lesson.penalty(kb.min_samples) + lesson.samples * 0.1,
        ))

    # Aggregate journal diagnostics.
    if journal:
        losers = [r for r in journal if r.is_loss]
        loss_rate = len(losers) / len(journal)
        avg_loss = sum(r.return_pct for r in losers) / len(losers) if losers else 0.0
        avg_win = (
            sum(r.return_pct for r in journal if not r.is_loss) / max(1, len(journal) - len(losers))
        )
        if loss_rate > 0.6 and len(journal) >= 20:
            proposals.append(Proposal(
                title="Overall loss rate elevated",
                rationale=f"{loss_rate:.0%} of {len(journal)} trades were losers.",
                suggested_change="Raise conviction floor and/or min_rr; trade less, wait for better edges.",
                evidence_samples=len(journal),
                priority=8.0,
            ))
        if avg_win and abs(avg_loss) > avg_win:
            proposals.append(Proposal(
                title="Average loss exceeds average win",
                rationale=f"avg_win={avg_win:.2%}, avg_loss={avg_loss:.2%}.",
                suggested_change="Tighten exits / let winners run further; review RR targets.",
                evidence_samples=len(journal),
                priority=6.0,
            ))

    return sorted(proposals, key=lambda p: p.priority, reverse=True)
