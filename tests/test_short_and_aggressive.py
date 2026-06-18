"""Regression guard: the bot must take SHORTs (conviction oriented by direction),
and the aggressive profile must act more readily than high."""

from app.agents import build_agents
from app.agents.cio_agent import CIOAgent
from app.core.config import apply_risk_profile, load_config
from app.core.constants import Action, MarketRegime
from app.data import indicators as ind
from app.data.market_data import trending_ohlcv
from app.decision.adaptive_risk import adapt_risk
from app.models import RegimeAssessment
from app.scoring.vote_engine import aggregate


def _idea_for(direction, profile="high"):
    s = apply_risk_profile(load_config(), profile)
    agents = build_agents()
    df = ind.enrich(trending_ohlcv("X", direction=direction, bars=320))
    data = {"1D": df, "1W": df, "_context": {"relative_strength": 0.0, "macro_score": 0,
            "breadth": None, "news": {}, "sentiment": {}}}
    agg = aggregate([a.analyze("X", data) for a in agents])
    regime = RegimeAssessment(regime=MarketRegime.SIDEWAYS, confidence=0.6, reasoning="t")
    rp = adapt_risk(base_risk=s.risk.risk_per_trade, regime=MarketRegime.SIDEWAYS)  # shorts allowed
    last = float(df["close"].iloc[-1]); atr = float(df["atr"].iloc[-1])
    return CIOAgent(s).form_idea(asset="X", agg=agg, regime=regime, last_price=last,
                                 atr=atr, risk_params=rp, df=df), agg


def test_bot_can_short_a_downtrend():
    idea, agg = _idea_for(direction=-1)
    assert agg.directional_bias < 0          # bearish signal exists
    assert idea is not None and idea.action == Action.SHORT
    assert idea.conviction > 0               # bug was: short conviction clamped to 0


def test_bot_longs_an_uptrend():
    idea, agg = _idea_for(direction=1)
    assert idea is not None and idea.action == Action.LONG and idea.conviction > 0


def test_aggressive_more_active_than_high():
    base = load_config()
    high = apply_risk_profile(base, "high")
    agg = apply_risk_profile(base, "aggressive")
    assert agg.conviction.bias_threshold < high.conviction.bias_threshold
    assert agg.conviction.flat_below < high.conviction.flat_below
    assert agg.risk.min_rr < high.risk.min_rr
    # Guardrails intact even in aggressive.
    assert agg.risk.default_leverage == 1.0
    assert agg.risk.min_rr > 1.0 and agg.execution.cost_aware is True
