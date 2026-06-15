"""Technical indicators implemented in pure pandas/numpy.

No TA-Lib dependency: easier to install, fully testable, and we control the
exact formula (important for reproducible backtests). Every function takes and
returns pandas Series/DataFrames aligned on the input index.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def hull_ma(series: pd.Series, period: int) -> pd.Series:
    """Hull Moving Average — smoother, lower lag."""
    half = max(int(period / 2), 1)
    sqrt_p = max(int(np.sqrt(period)), 1)
    wma_half = _wma(series, half)
    wma_full = _wma(series, period)
    return _wma(2 * wma_half - wma_full, sqrt_p)


def _wma(series: pd.Series, period: int) -> pd.Series:
    weights = np.arange(1, period + 1)
    return series.rolling(period).apply(
        lambda x: np.dot(x, weights) / weights.sum(), raw=True
    )


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(100 - (100 / (1 + 0)))  # all-gains edge case -> ~100


def macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "hist": hist})


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def adx(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    """Average Directional Index — trend strength (not direction)."""
    up = high.diff()
    down = -low.diff()
    plus_dm = ((up > down) & (up > 0)) * up
    minus_dm = ((down > up) & (down > 0)) * down
    tr = true_range(high, low, close)
    atr_ = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def bollinger(
    series: pd.Series, period: int = 20, num_std: float = 2.0
) -> pd.DataFrame:
    mid = sma(series, period)
    std = series.rolling(period, min_periods=period).std()
    return pd.DataFrame(
        {"mid": mid, "upper": mid + num_std * std, "lower": mid - num_std * std}
    )


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def vwap(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series
) -> pd.Series:
    typical = (high + low + close) / 3
    cum_vol = volume.cumsum().replace(0, np.nan)
    return (typical * volume).cumsum() / cum_vol


def roc(series: pd.Series, period: int = 12) -> pd.Series:
    return series.pct_change(period) * 100


def stochastic_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    r = rsi(series, period)
    lo = r.rolling(period, min_periods=period).min()
    hi = r.rolling(period, min_periods=period).max()
    return ((r - lo) / (hi - lo).replace(0, np.nan)).clip(0, 1)


def realized_volatility(close: pd.Series, period: int = 20, annualize: int = 252) -> pd.Series:
    """Annualized rolling volatility of log returns."""
    log_ret = np.log(close / close.shift(1))
    return log_ret.rolling(period, min_periods=period).std() * np.sqrt(annualize)


def supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 10,
    multiplier: float = 3.0,
) -> pd.DataFrame:
    """Supertrend trend-following overlay. Returns line + direction (+1/-1)."""
    atr_ = atr(high, low, close, period)
    hl2 = (high + low) / 2
    upper = hl2 + multiplier * atr_
    lower = hl2 - multiplier * atr_

    n = len(close)
    trend = np.ones(n)
    line = np.full(n, np.nan)
    for i in range(1, n):
        if np.isnan(atr_.iloc[i]):
            continue
        if close.iloc[i] > upper.iloc[i - 1]:
            trend[i] = 1
        elif close.iloc[i] < lower.iloc[i - 1]:
            trend[i] = -1
        else:
            trend[i] = trend[i - 1]
            if trend[i] == 1:
                lower.iloc[i] = max(lower.iloc[i], lower.iloc[i - 1])
            else:
                upper.iloc[i] = min(upper.iloc[i], upper.iloc[i - 1])
        line[i] = lower.iloc[i] if trend[i] == 1 else upper.iloc[i]
    return pd.DataFrame({"supertrend": line, "direction": trend}, index=close.index)


def enrich(df: pd.DataFrame, ema_periods: tuple[int, ...] = (20, 50, 100, 200)) -> pd.DataFrame:
    """Attach the standard indicator panel to an OHLCV frame.

    Expects columns: open, high, low, close, volume (lowercase).
    """
    out = df.copy()
    close, high, low, vol = out["close"], out["high"], out["low"], out["volume"]
    for p in ema_periods:
        out[f"ema{p}"] = ema(close, p)
    out["rsi"] = rsi(close)
    macd_df = macd(close)
    out["macd"] = macd_df["macd"]
    out["macd_signal"] = macd_df["signal"]
    out["macd_hist"] = macd_df["hist"]
    out["atr"] = atr(high, low, close)
    out["adx"] = adx(high, low, close)
    bb = bollinger(close)
    out["bb_upper"], out["bb_mid"], out["bb_lower"] = bb["upper"], bb["mid"], bb["lower"]
    out["obv"] = obv(close, vol)
    out["roc"] = roc(close)
    out["rvol"] = realized_volatility(close)
    out["vol_sma"] = sma(vol, 20)
    return out
