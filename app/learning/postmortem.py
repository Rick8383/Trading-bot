"""Post-mortem analyzer: turn a closed trade into structured error tags.

This is the "auto-analyse pour trouver la solution" step. For every closed
trade we ask: given what we knew, what category of mistake (if any) does this
outcome reveal? Tags are intentionally about *context*, not the individual
asset — so the lesson generalizes (e.g. "longs taken with an MTF trend conflict
lose money") instead of merely "AAPL lost".
"""

from __future__ import annotations

from dataclasses import dataclass

from app.learning.trade_journal import TradeRecord


@dataclass(frozen=True)
class ErrorTag:
    key: str            # stable identifier used by the knowledge base
    description: str
    remedy: str         # suggested corrective action (human-readable)


# Catalogue of known failure modes and their remedies.
def _against_regime(rec: TradeRecord) -> bool:
    bullish = rec.regime in ("bull", "recovery")
    bearish = rec.regime in ("bear", "crash")
    if rec.action == "LONG" and bearish:
        return True
    if rec.action == "SHORT" and bullish:
        return True
    return False


def setup_signature(
    *, action: str, regime: str, conviction: float, reward_risk: float, risk_flags: list[str]
) -> list[str]:
    """Canonical context keys describing a setup, derivable *before* the trade.

    Used at decision time to look up learned penalties, and after close to
    attribute the outcome to the same keys. This symmetry is what makes the
    feedback loop statistically honest: a context is only penalized once both
    its wins and losses say it is a net loser.
    """
    keys: list[str] = []
    bullish = regime in ("bull", "recovery")
    bearish = regime in ("bear", "crash")
    if (action == "LONG" and bearish) or (action == "SHORT" and bullish):
        keys.append(f"regime_misalignment:{regime}")
    if conviction < 60:
        keys.append("low_conviction")
    if regime in ("high_vol", "crash"):
        keys.append(f"vol_env:{regime}")
    if reward_risk and reward_risk < 2.0:
        keys.append("thin_reward_risk")
    for flag in risk_flags:
        keys.append(f"flag:{flag}")
    return keys


def signature_for_record(rec: TradeRecord) -> list[str]:
    return setup_signature(
        action=rec.action, regime=rec.regime, conviction=rec.conviction,
        reward_risk=rec.reward_risk, risk_flags=rec.risk_flags,
    )


def post_mortem(rec: TradeRecord) -> list[ErrorTag]:
    """Return error tags for a *losing* trade. Winners yield no error tags but
    are still recorded (the knowledge base tracks both to compute expectancy).
    """
    tags: list[ErrorTag] = []
    if not rec.is_loss:
        return tags  # nothing went "wrong"; KB still counts it as a positive sample

    if _against_regime(rec):
        tags.append(ErrorTag(
            f"regime_misalignment:{rec.regime}",
            f"Took a {rec.action} trade against a {rec.regime} regime and lost.",
            "Require stronger confirmation (or block) trades against the prevailing regime.",
        ))

    if rec.conviction < 60:
        tags.append(ErrorTag(
            "low_conviction_loss",
            f"Entered at conviction {rec.conviction:.0f} (<60) and lost.",
            "Raise the minimum conviction floor or down-weight marginal setups.",
        ))

    if rec.regime in ("high_vol", "crash"):
        tags.append(ErrorTag(
            f"loss_in_{rec.regime}",
            f"Lost in a {rec.regime} environment.",
            "Cut size / stand aside in elevated-volatility regimes.",
        ))

    if rec.reward_risk < 2.0:
        tags.append(ErrorTag(
            "thin_reward_risk_loss",
            f"Lost on a thin reward/risk of {rec.reward_risk:.2f}.",
            "Enforce the RR>=2 floor more strictly; reject thin setups.",
        ))

    # Each decision-time risk flag that preceded a loss becomes a lesson.
    for flag in rec.risk_flags:
        tags.append(ErrorTag(
            f"risk_flag_loss:{flag}",
            f"Lost on a setup that carried the '{flag}' risk flag.",
            f"Penalize conviction when '{flag}' is present.",
        ))

    if rec.reason == "stop_loss" and abs(rec.return_pct) < 0.01:
        tags.append(ErrorTag(
            "stop_too_tight",
            "Stopped out almost immediately for a tiny loss — likely noise.",
            "Widen stops relative to ATR or improve entry timing.",
        ))

    return tags
