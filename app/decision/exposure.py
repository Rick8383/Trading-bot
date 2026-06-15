"""Portfolio exposure controller.

Enforces gross/net/short caps, per-asset caps and the max-position count.
Operates on intended target weights and clips them to the feasible set. This is
a *portfolio* constraint layer, distinct from the per-trade risk veto.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import RiskConfig
from app.core.constants import Action


@dataclass
class Position:
    asset: str
    action: Action
    weight: float            # signed fraction of equity (long +, short -)


@dataclass
class ExposureReport:
    gross: float
    net: float
    short: float
    n_positions: int
    breaches: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.breaches


def summarize(positions: list[Position]) -> ExposureReport:
    longs = sum(p.weight for p in positions if p.weight > 0)
    shorts = sum(-p.weight for p in positions if p.weight < 0)
    gross = longs + shorts
    net = longs - shorts
    return ExposureReport(gross=gross, net=net, short=shorts, n_positions=len(positions))


def check_limits(
    positions: list[Position], risk: RiskConfig, exposure_cap: float | None = None
) -> ExposureReport:
    """Return a report listing every breached limit (empty == feasible)."""
    rep = summarize(positions)
    cap = risk.max_gross_exposure if exposure_cap is None else min(risk.max_gross_exposure, exposure_cap)

    if rep.gross > cap + 1e-9:
        rep.breaches.append(f"gross {rep.gross:.2f} > cap {cap:.2f}")
    if abs(rep.net) > risk.max_net_exposure + 1e-9:
        rep.breaches.append(f"net {rep.net:.2f} > max {risk.max_net_exposure:.2f}")
    if rep.short > risk.max_short_exposure + 1e-9:
        rep.breaches.append(f"short {rep.short:.2f} > max {risk.max_short_exposure:.2f}")
    if rep.n_positions > risk.max_positions:
        rep.breaches.append(f"positions {rep.n_positions} > max {risk.max_positions}")
    for p in positions:
        if abs(p.weight) > risk.max_asset_exposure + 1e-9:
            rep.breaches.append(
                f"{p.asset} weight {abs(p.weight):.2f} > max {risk.max_asset_exposure:.2f}"
            )
    return rep


def can_add(
    existing: list[Position], candidate: Position, risk: RiskConfig, exposure_cap: float | None = None
) -> tuple[bool, str]:
    """Would adding ``candidate`` keep the portfolio within all limits?"""
    rep = check_limits([*existing, candidate], risk, exposure_cap)
    if rep.ok:
        return True, "within limits"
    return False, "; ".join(rep.breaches)
