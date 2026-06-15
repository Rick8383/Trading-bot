"""Broker abstraction shared by paper and live adapters.

Every broker — simulated or real — must honor the cardinal rule: an order
without a valid stop is refused. The live adapters call ``validate`` before any
network submit, exactly like the paper broker, so the guardrail holds end to end.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.execution.order_validator import Order


@runtime_checkable
class Broker(Protocol):
    """Minimal surface the orchestration layer depends on."""

    def submit(self, order: Order, decision_ref: str | None = None): ...

    def close(self, symbol: str, price: float, reason: str = "manual"): ...

    def mark_to_market(self, marks: dict[str, float]) -> list: ...

    def equity(self, marks: dict[str, float]) -> float: ...
