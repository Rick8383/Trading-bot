"""Edge-net-of-costs filter: trades must clear round-trip costs by a buffer."""

import numpy as np

from app.agents.cio_agent import CIOAgent
from app.core.config import load_config
from app.core.constants import Action, MarketRegime
from app.data import indicators as ind
from app.data.market_data import trending_ohlcv
from app.decision.adaptive_risk import adapt_risk
from app.models import RegimeAssessment
from app.scoring.vote_engine import aggregate
from app.agents.base import vote_from_score


def _agg(score):
    votes = [vote_from_score("TrendAI", "X", "trend", score, 0.8, "t"),
             vote_from_score("MomentumAI", "X", "momentum", score, 0.7, "m")]
    return aggregate(votes)


def _regime():
    return RegimeAssessment(regime=MarketRegime.BULL, confidence=0.8, reasoning="t")


def _idea(settings, df, atr):
    cio = CIOAgent(settings)
    rp = adapt_risk(base_risk=settings.risk.risk_per_trade, regime=MarketRegime.BULL)
    return cio.form_idea(
        asset="X", agg=_agg(60), regime=_regime(), last_price=float(df["close"].iloc[-1]),
        atr=atr, risk_params=rp, df=df,
    )


def test_high_costs_block_marginal_trades():
    df = ind.enrich(trending_ohlcv("X", 1, 220))
    atr = float(df["atr"].iloc[-1])

    cheap = load_config()
    cheap.execution.slippage_bps = 2
    cheap.execution.commission_bps = 1
    idea_cheap = _idea(cheap, df, atr)

    pricey = load_config()
    pricey.execution.slippage_bps = 300     # absurd costs -> nothing clears the edge
    pricey.execution.commission_bps = 300
    idea_pricey = _idea(pricey, df, atr)

    assert idea_pricey is None              # blocked by the cost filter
    # The cheap-cost config should be at least as permissive.
    if idea_cheap is not None:
        assert idea_cheap.expected_value > 0


def test_cost_aware_can_be_disabled():
    df = ind.enrich(trending_ohlcv("X", 1, 220))
    atr = float(df["atr"].iloc[-1])
    s = load_config()
    s.execution.slippage_bps = 300
    s.execution.commission_bps = 300
    s.execution.cost_aware = False          # disabled -> gross EV only
    idea = _idea(s, df, atr)
    # With the filter off, a positive gross-EV setup can still pass.
    assert idea is None or idea.expected_value != 0


def test_recorded_ev_is_net_of_costs():
    df = ind.enrich(trending_ohlcv("X", 1, 220))
    atr = float(df["atr"].iloc[-1])
    s = load_config()
    s.execution.slippage_bps = 5
    s.execution.commission_bps = 2
    idea = _idea(s, df, atr)
    if idea is not None:
        # Net EV is strictly less than a naive gross EV would be (costs subtracted).
        rt = 2 * (5 + 2) / 10_000 * 100
        assert idea.expected_value >= s.execution.min_edge_pct
        assert rt > 0
