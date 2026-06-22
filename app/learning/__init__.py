"""Self-improvement loop — the system's memory and conscience.

Flow:
    decision + outcome  ->  TradeJournal (durable record)
                        ->  post-mortem  (tag what went right/wrong)
                        ->  KnowledgeBase (aggregate lessons, persist)
                        ->  conviction penalties fed back into the CIO
                        ->  ImprovementEngine (propose param changes, NEVER auto-deploy)

The promise to the founder: the bot remembers its mistakes, finds *why* they
happened, and docks conviction from setups that resemble past losers — so it
stops repeating them and gets sharper over time. Nothing here can place a trade
or change risk limits on its own; it only proposes and penalizes.
"""

from app.learning.knowledge_base import KnowledgeBase, Lesson
from app.learning.postmortem import ErrorTag, post_mortem
from app.learning.trade_journal import TradeJournal, TradeRecord

__all__ = [
    "KnowledgeBase",
    "Lesson",
    "ErrorTag",
    "post_mortem",
    "TradeJournal",
    "TradeRecord",
]
