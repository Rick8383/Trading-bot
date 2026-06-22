"""Conviction engine: blend agent scores into a single 0-100 conviction, then
map conviction to an allocation factor — progressively, never with a binary
cliff at an arbitrary threshold.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import ConvictionConfig

# Default blend weights for the conviction score. Mirrors the spec; the CIO can
# override per regime. Keys are agent *roles*, not class names.
DEFAULT_WEIGHTS: dict[str, float] = {
    "trend": 0.25,
    "momentum": 0.20,
    "regime": 0.15,
    "volume": 0.10,
    "pattern": 0.10,
    "quant": 0.10,
    "macro": 0.10,
}


def compute_conviction(scores: dict[str, float], weights: dict[str, float] | None = None) -> float:
    """Weighted blend of role scores (each 0-100) into a 0-100 conviction.

    Missing roles are simply skipped and the weights renormalized over the
    roles we actually have, so a partial agent set still yields a sane number.
    """
    weights = weights or DEFAULT_WEIGHTS
    present = {k: weights[k] for k in scores if k in weights}
    total_w = sum(present.values())
    if total_w <= 0:
        return 0.0
    blended = sum(scores[k] * present[k] for k in present) / total_w
    return float(max(0.0, min(100.0, blended)))


@dataclass(frozen=True)
class AllocationBand:
    label: str
    floor: float          # min fraction of max-allowed size
    ceil: float           # max fraction of max-allowed size


def allocation_factor(conviction: float, cfg: ConvictionConfig | None = None) -> float:
    """Map conviction -> fraction of the *risk-bounded* max size, smoothly.

    The result is always bounded by the per-trade risk budget elsewhere; this
    only modulates *within* that budget. No emotion, just conviction.
    """
    cfg = cfg or ConvictionConfig()
    c = max(0.0, min(100.0, conviction))
    if c < cfg.flat_below:                       # 0-40  -> nothing
        return 0.0
    if c < cfg.reduced_below:                     # 40-60 -> 25%..50%
        return _lerp(c, cfg.flat_below, cfg.reduced_below, 0.25, 0.50)
    if c < cfg.standard_below:                     # 60-80 -> 50%..80%
        return _lerp(c, cfg.reduced_below, cfg.standard_below, 0.50, 0.80)
    return _lerp(c, cfg.standard_below, 100.0, 0.80, 1.00)  # 80-100 -> 80%..100%


def conviction_band(conviction: float, cfg: ConvictionConfig | None = None) -> str:
    cfg = cfg or ConvictionConfig()
    if conviction < cfg.flat_below:
        return "NO_TRADE"
    if conviction < cfg.reduced_below:
        return "WATCHLIST"
    if conviction < cfg.standard_below:
        return "VALID_SIGNAL"
    return "HIGH_CONVICTION"


def _lerp(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    if x1 == x0:
        return y1
    t = (x - x0) / (x1 - x0)
    return y0 + t * (y1 - y0)
