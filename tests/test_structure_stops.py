import numpy as np
import pandas as pd

from app.core.constants import Action
from app.data import indicators as ind
from app.data.market_data import trending_ohlcv
from app.risk.stop_manager import atr_stop, structure_stop, structure_target
from app.strategies.structure_levels import (
    nearest_resistance,
    nearest_support,
    support_resistance,
)


def _df():
    return ind.enrich(trending_ohlcv("X", direction=1, bars=200))


def test_support_below_and_resistance_above():
    df = _df()
    price = float(df["close"].iloc[-1])
    s = nearest_support(df, price)
    r = nearest_resistance(df, price)
    assert s is None or s < price
    assert r is None or r > price


def test_support_resistance_nonempty_on_real_series():
    sup, res = support_resistance(_df())
    assert len(sup) >= 1 and len(res) >= 1


def test_structure_stop_is_below_entry_for_long():
    df = _df()
    entry = float(df["close"].iloc[-1])
    atr = float(df["atr"].iloc[-1])
    stop = structure_stop(df, entry, atr, Action.LONG, multiplier=2.5)
    assert stop < entry
    # Bounded by ATR sane band: never absurdly far (>3x) or tighter than 0.5x.
    dist = entry - stop
    assert 0.5 * atr * 2.5 - 1e-6 <= dist <= 3.0 * atr * 2.5 + 1e-6


def test_structure_stop_falls_back_to_atr_when_level_out_of_band():
    # Flat base ~100 then a far spike: the only support is ~30 away while the
    # ATR distance is 2.5 -> out of the sane band -> fall back to the ATR stop.
    idx = pd.date_range("2020-01-01", periods=56, freq="D")
    close = [100.0] * 55 + [130.0]
    df = pd.DataFrame({
        "open": close, "high": [c + 0.3 for c in close],
        "low": [c - 0.3 for c in close], "close": close, "volume": [1000.0] * 56,
    }, index=idx)
    entry = 130.0
    stop = structure_stop(df, entry, atr=1.0, action=Action.LONG, multiplier=2.5)
    assert stop == atr_stop(entry, 1.0, Action.LONG, 2.5)


def test_structure_target_respects_min_rr():
    df = _df()
    entry = float(df["close"].iloc[-1])
    stop = entry - 2.0
    target = structure_target(df, entry, stop, Action.LONG, min_rr=2.0)
    rr = (target - entry) / (entry - stop)
    assert rr >= 2.0 - 1e-9


def test_structure_stop_short_is_above_entry():
    df = ind.enrich(trending_ohlcv("Y", direction=-1, bars=200))
    entry = float(df["close"].iloc[-1])
    atr = float(df["atr"].iloc[-1])
    stop = structure_stop(df, entry, atr, Action.SHORT, multiplier=2.5)
    assert stop > entry
