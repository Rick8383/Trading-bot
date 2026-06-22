"""Adaptive, regime-aware risk parameters — with hard anti-bias guards.

The single most important guard here: per-trade risk does NOT increase after a
winning streak. Confidence is not edge. We modulate risk *down* in adverse
regimes and after losses, never *up* on euphoria.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.constants import MarketRegime

# Regime -> (risk multiplier, gross-exposure cap, shorts allowed)
_REGIME_RULES: dict[MarketRegime, tuple[float, float, bool]] = {
    MarketRegime.BULL: (1.0, 1.00, False),
    MarketRegime.RECOVERY: (0.6, 0.60, False),
    MarketRegime.SIDEWAYS: (0.7, 0.50, True),
    MarketRegime.BEAR: (0.6, 0.50, True),
    MarketRegime.HIGH_VOL: (0.5, 0.40, True),
    MarketRegime.CRASH: (0.0, 0.00, False),
}


@dataclass(frozen=True)
class RiskParams:
    risk_per_trade: float
    gross_exposure_cap: float
    shorts_allowed: bool
    reason: str


def adapt_risk(
    *,
    base_risk: float,
    regime: MarketRegime,
    realized_vol: float | None = None,
    target_vol: float = 0.20,
    consecutive_losses: int = 0,
) -> RiskParams:
    """Compute effective per-trade risk and exposure cap for current conditions.

    Volatility targeting: if realized vol exceeds the target, scale size down so
    the *dollar* risk stays roughly constant. We never scale risk above base.
    """
    mult, cap, shorts = _REGIME_RULES.get(regime, (0.7, 0.5, True))
    risk = base_risk * mult
    reasons = [f"regime={regime.value} mult={mult}"]

    # Volatility targeting (scale down only).
    if realized_vol and realized_vol > 0:
        vol_scale = min(1.0, target_vol / realized_vol)
        if vol_scale < 1.0:
            risk *= vol_scale
            reasons.append(f"vol_target scale={vol_scale:.2f}")

    # After losses, de-risk further. After WINS we deliberately do nothing.
    if consecutive_losses >= 3:
        risk *= 0.5
        reasons.append(f"{consecutive_losses} consecutive losses -> halve risk")
    elif consecutive_losses == 2:
        risk *= 0.75
        reasons.append("2 consecutive losses -> 0.75x risk")

    # Hard ceiling: effective risk can never exceed the configured base.
    risk = min(risk, base_risk)
    return RiskParams(risk, cap, shorts, "; ".join(reasons))
