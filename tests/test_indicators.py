import numpy as np
import pandas as pd

from app.data import indicators as ind
from app.data.market_data import synthetic_ohlcv


def test_synthetic_is_deterministic():
    a = synthetic_ohlcv("BTC")
    b = synthetic_ohlcv("BTC")
    pd.testing.assert_frame_equal(a, b)
    assert not synthetic_ohlcv("ETH")["close"].equals(a["close"])


def test_ohlc_consistency():
    df = synthetic_ohlcv("X")
    assert (df["high"] >= df["low"]).all()
    assert (df["high"] >= df["close"]).all()
    assert (df["low"] <= df["close"]).all()


def test_rsi_bounds():
    df = synthetic_ohlcv("X")
    r = ind.rsi(df["close"]).dropna()
    assert (r >= 0).all() and (r <= 100).all()


def test_ema_tracks_uptrend():
    s = pd.Series(np.arange(1, 300, dtype=float))
    e = ind.ema(s, 20).dropna()
    # On a monotonic rising series the EMA must also rise.
    assert e.iloc[-1] > e.iloc[0]


def test_atr_positive():
    df = synthetic_ohlcv("X")
    a = ind.atr(df["high"], df["low"], df["close"]).dropna()
    assert (a > 0).all()


def test_enrich_adds_columns():
    df = synthetic_ohlcv("X")
    out = ind.enrich(df)
    for col in ("ema20", "ema200", "rsi", "macd_hist", "atr", "adx", "obv", "rvol"):
        assert col in out.columns
