"""Provider tests — offline-safe (no network required).

We test the caching wrapper and resampling against a stub provider, and verify
the synthetic fallback path triggers cleanly when a provider raises.
"""

import pandas as pd
import pytest

from app.data.market_data import MarketDataProvider, synthetic_ohlcv
from app.data.providers import CachingProvider, resample_ohlcv


class _StubProvider(MarketDataProvider):
    def __init__(self):
        super().__init__(synthetic=False)
        self.calls = 0

    def get_ohlcv(self, symbol, timeframe="1D", bars=500):
        self.calls += 1
        return synthetic_ohlcv(symbol)


class _BrokenProvider(MarketDataProvider):
    def __init__(self):
        super().__init__(synthetic=False)

    def get_ohlcv(self, symbol, timeframe="1D", bars=500):
        raise ConnectionError("simulated network egress block")


def test_resample_daily_to_weekly():
    df = synthetic_ohlcv("X")
    weekly = resample_ohlcv(df, "1W")
    assert len(weekly) < len(df)
    assert list(weekly.columns) == ["open", "high", "low", "close", "volume"]
    # Weekly high must be >= weekly close (OHLC integrity preserved).
    assert (weekly["high"] >= weekly["close"]).all()


def test_caching_avoids_refetch(tmp_path):
    stub = _StubProvider()
    cp = CachingProvider(stub, cache_dir=str(tmp_path), max_age_hours=12)
    a = cp.get_ohlcv("BTC/USDT", "1D", 300)
    b = cp.get_ohlcv("BTC/USDT", "1D", 300)
    assert stub.calls == 1                       # second call served from cache
    assert cp.last_source["BTC/USDT"] == "cache"
    # Values must match; index freq metadata is lost through CSV and irrelevant.
    pd.testing.assert_frame_equal(a, b, check_freq=False)


def test_caching_falls_back_to_synthetic_on_error(tmp_path):
    cp = CachingProvider(_BrokenProvider(), cache_dir=str(tmp_path), fallback_synthetic=True)
    df = cp.get_ohlcv("ZZZ", "1D", 300)
    assert len(df) > 0
    assert cp.last_source["ZZZ"] == "synthetic_fallback"


def test_caching_raises_without_fallback(tmp_path):
    cp = CachingProvider(_BrokenProvider(), cache_dir=str(tmp_path), fallback_synthetic=False)
    with pytest.raises(RuntimeError):
        cp.get_ohlcv("ZZZ", "1D", 300)
