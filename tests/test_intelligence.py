import numpy as np
import pandas as pd

from app.agents import build_agents
from app.agents.ml_agent import MLAgent, _NumpyLogReg
from app.agents.smc_agent import SMCAgent
from app.backtesting.walk_forward import DEFAULT_GRID, walk_forward
from app.core.constants import Vote
from app.data import indicators as ind
from app.data.market_data import SyntheticConfig, synthetic_ohlcv, trending_ohlcv
from app.strategies.smc import analyze_smc, detect_bos_choch, detect_fvg


def _frames(symbol, direction=1, bars=320):
    df = ind.enrich(trending_ohlcv(symbol, direction=direction, bars=bars))
    return {tf: df for tf in ("1D", "1W")}


# --- SMC --------------------------------------------------------------

def test_fvg_detects_bullish_gap():
    # Construct a clean bullish FVG: candle i low above candle i-2 high.
    df = pd.DataFrame({
        "open": [10, 11, 13], "high": [10.5, 12, 14],
        "low": [9.5, 10.5, 11], "close": [10, 11.5, 13], "volume": [1, 1, 1],
    })
    # pad to >=30 rows of flat then the gap at the end
    pad = pd.DataFrame({c: [10.0] * 30 for c in df.columns})
    full = pd.concat([pad, df], ignore_index=True)
    score, label = detect_fvg(full)
    assert label == "bullish_fvg" and score > 0


def test_bos_choch_directional():
    up = ind.enrich(trending_ohlcv("UP", 1, 200))
    score, _ = detect_bos_choch(up)
    assert score >= 0  # an uptrend should not flag bearish structure breaks


def test_smc_agent_valid_vote():
    v = SMCAgent().analyze("X", _frames("X", 1))
    assert -100 <= v.score <= 100
    assert v.confidence <= 0.4  # low by design
    assert v.features["role"] == "pattern"


def test_analyze_smc_bounded():
    sig = analyze_smc(ind.enrich(synthetic_ohlcv("X")))
    assert -100 <= sig.score <= 100


# --- ML ---------------------------------------------------------------

def test_numpy_logreg_learns_separable():
    rng = np.random.default_rng(0)
    X = np.vstack([rng.normal(-2, 1, (100, 2)), rng.normal(2, 1, (100, 2))])
    y = np.array([0.0] * 100 + [1.0] * 100)
    m = _NumpyLogReg(iters=300).fit(X, y)
    assert m.train_acc > 0.9


def test_ml_agent_abstains_on_short_history():
    short = {tf: ind.enrich(trending_ohlcv("X", 1, 80)) for tf in ("1D", "1W")}
    v = MLAgent().analyze("X", short)
    assert v.score == 0.0 and v.confidence <= 0.3


def test_ml_agent_produces_valid_vote_with_enough_data():
    v = MLAgent().analyze("X", _frames("X", 1, bars=320))
    assert -100 <= v.score <= 100
    assert 0 <= v.confidence <= 0.7
    assert v.features["role"] == "ml"
    assert v.direction in (Vote.BUY, Vote.SELL, Vote.HOLD)


def test_build_agents_includes_ml_when_requested():
    assert any(a.role == "ml" for a in build_agents(include_ml=True))
    assert not any(a.role == "ml" for a in build_agents(include_ml=False))
    assert any(a.role == "pattern" and a.name == "SMC_AI" for a in build_agents())


# --- walk-forward -----------------------------------------------------

def test_walk_forward_runs_out_of_sample():
    df = synthetic_ohlcv("WF", SyntheticConfig(bars=900, drift=0.0006, volatility=0.013))
    wf = walk_forward(df["close"], train=252, test=63)
    assert len(wf.windows) >= 3
    for w in wf.windows:
        assert w.chosen_params in DEFAULT_GRID
        # No look-ahead: test window strictly follows the train window.
        assert w.test[0] == w.train[1]
    assert len(wf.oos_equity) > 1
    assert 0 <= wf.selection_stability <= 1
