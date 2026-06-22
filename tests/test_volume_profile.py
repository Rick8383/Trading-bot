import numpy as np
import pandas as pd

from app.agents import DEFAULT_ANALYTIC_AGENTS
from app.agents.volume_profile_agent import VolumeProfileAgent
from app.data import indicators as ind
from app.data.market_data import trending_ohlcv
from app.strategies.structure_levels import support_resistance
from app.strategies.volume_profile import anchored_vwap, volume_profile


def _df():
    return ind.enrich(trending_ohlcv("X", 1, 200))


def test_volume_profile_levels_ordered():
    vp = volume_profile(_df())
    assert vp is not None
    assert vp.val <= vp.poc <= vp.vah
    assert len(vp.hvn) >= 1


def test_volume_profile_poc_at_high_volume_price():
    # Concentrate volume around price 100; POC should land near there.
    idx = pd.date_range("2020-01-01", periods=120, freq="D")
    close = np.r_[np.full(100, 100.0), np.linspace(100, 130, 20)]
    vol = np.r_[np.full(100, 5000.0), np.full(20, 200.0)]   # most volume at 100
    df = pd.DataFrame({"open": close, "high": close + 0.5, "low": close - 0.5,
                       "close": close, "volume": vol}, index=idx)
    vp = volume_profile(df, bins=24, lookback=120)
    assert abs(vp.poc - 100.0) < 3.0


def test_anchored_vwap_within_range():
    df = _df()
    vwap = anchored_vwap(df, anchor_bars=60)
    assert df["low"].tail(60).min() <= vwap <= df["high"].tail(60).max()


def test_structure_levels_include_volume_nodes():
    df = _df()
    sup, res = support_resistance(df)
    vp = volume_profile(df, lookback=100)   # match support_resistance's lookback
    alllevels = sup + res
    # POC should appear among the candidate levels.
    assert any(abs(l - vp.poc) < 1e-6 for l in alllevels)


def test_volume_profile_agent_valid_vote():
    frames = {tf: _df() for tf in ("1D", "1W")}
    v = VolumeProfileAgent().analyze("X", frames)
    assert -100 <= v.score <= 100
    assert v.features["role"] == "volume"
    assert "poc" in v.features


def test_volume_profile_agent_in_default_roster():
    assert any(a.name == "VolumeProfileAI" for a in DEFAULT_ANALYTIC_AGENTS)
