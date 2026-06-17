import numpy as np

from app.agents import build_agents
from app.agents.cio_agent import CIOAgent
from app.agents.ml_agent import MLAgent, _platt_apply, _platt_fit
from app.core.config import load_config
from app.core.constants import Action
from app.data import indicators as ind
from app.data.market_data import trending_ohlcv
from app.models import AgentVote
from app.scoring.vote_engine import aggregate
from app.strategies.regime import classify_regime


def test_platt_calibration_monotone_and_bounded():
    raw = np.linspace(0.05, 0.95, 50)
    y = (raw > 0.5).astype(float)
    ab = _platt_fit(raw, y)
    lo = _platt_apply(0.1, ab)
    hi = _platt_apply(0.9, ab)
    assert 0.0 <= lo <= 1.0 and 0.0 <= hi <= 1.0
    assert hi > lo  # calibration preserves ordering


def test_ml_agent_emits_calibrated_prob():
    frames = {tf: ind.enrich(trending_ohlcv("X", 1, 320)) for tf in ("1D", "1W")}
    v = MLAgent().analyze("X", frames)
    assert 0.0 < v.features["p_up"] < 1.0
    assert "calibrated_acc" in v.features


def _ml_vote(asset, p_up, conf=0.5):
    return AgentVote(agent="ML_AI", asset=asset, buy=p_up, sell=1 - p_up, hold=0.0,
                     score=(p_up - 0.5) * 200, confidence=conf,
                     features={"role": "ml", "p_up": p_up})


def test_cio_blends_ml_prob_into_win_prob():
    cio = CIOAgent(load_config())
    # A bullish ML probability pulls the long win_prob above the conviction prior.
    agg_hi = aggregate([_ml_vote("X", 0.75)])
    agg_lo = aggregate([_ml_vote("X", 0.25)])
    assert cio._ml_win_prob(agg_hi, Action.LONG) == 0.75
    assert cio._ml_win_prob(agg_lo, Action.LONG) == 0.25
    # Short side inverts the probability.
    assert cio._ml_win_prob(agg_hi, Action.SHORT) == 0.25


def test_cio_ignores_low_confidence_ml():
    cio = CIOAgent(load_config())
    agg = aggregate([_ml_vote("X", 0.9, conf=0.1)])  # below the 0.3 floor
    assert cio._ml_win_prob(agg, Action.LONG) is None


def test_build_agents_with_ml_includes_role():
    assert any(a.role == "ml" for a in build_agents(include_ml=True))
