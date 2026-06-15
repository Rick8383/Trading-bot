"""Real market-data connectors (Phase 2) with caching + graceful fallback.

Design goals:
  * Work on the founder's machine / any host with open egress (real candles).
  * Never crash a run if the network is blocked — fall back to synthetic data
    and clearly flag the source.
  * Cache every fetch to disk so subsequent runs are fast and work offline.

Symbol routing:
  * "BTC/USDT"  -> crypto exchange via ccxt (public OHLCV, no API key needed).
  * "SPY", "AAPL" -> equities/ETF via yfinance.

Both connectors are *optional imports*: the core never hard-depends on them.
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from app.core.logging import get_logger
from app.data.market_data import MarketDataProvider, SyntheticConfig, synthetic_ohlcv

_log = get_logger("data")

# Our timeframe labels -> (ccxt code, yfinance interval, pandas resample rule)
_CCXT_TF = {"1H": "1h", "4H": "4h", "1D": "1d", "1W": "1w"}
_YF_INTERVAL = {"1H": "60m", "4H": "60m", "1D": "1d", "1W": "1wk"}
_RESAMPLE = {"4H": "4h", "1W": "1W"}

_OHLCV_AGG = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample an OHLCV frame to a coarser timeframe (e.g. 1D -> 1W)."""
    out = df.resample(rule).agg(_OHLCV_AGG).dropna(how="any")
    return out


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase OHLCV columns, ensure a sorted DatetimeIndex."""
    df = df.rename(columns={c: str(c).lower() for c in df.columns})
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    df = df[keep].copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    return df.sort_index().dropna(how="any")


class CachingProvider(MarketDataProvider):
    """Wraps a real provider with a CSV disk cache + synthetic fallback."""

    def __init__(self, inner: MarketDataProvider, cache_dir: str = "data_store/cache",
                 max_age_hours: float = 12.0, fallback_synthetic: bool = True):
        super().__init__(synthetic=False)
        self.inner = inner
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_age = max_age_hours * 3600
        self.fallback_synthetic = fallback_synthetic
        self.last_source: dict[str, str] = {}

    def _cache_path(self, symbol: str, timeframe: str) -> Path:
        safe = symbol.replace("/", "_").replace(":", "_")
        return self.cache_dir / f"{type(self.inner).__name__}_{safe}_{timeframe}.csv"

    def get_ohlcv(self, symbol: str, timeframe: str = "1D", bars: int = 500) -> pd.DataFrame:
        path = self._cache_path(symbol, timeframe)

        # 1) Fresh cache hit.
        if path.exists() and (time.time() - path.stat().st_mtime) < self.max_age:
            self.last_source[symbol] = "cache"
            return _normalize(pd.read_csv(path, index_col=0, parse_dates=True)).tail(bars)

        # 2) Try the real provider.
        try:
            df = _normalize(self.inner.get_ohlcv(symbol, timeframe, bars))
            if len(df):
                df.to_csv(path)
                self.last_source[symbol] = "live"
                return df.tail(bars)
        except Exception as exc:  # noqa: BLE001 — network/parse errors are expected sometimes
            _log.warning("data_fetch_failed", symbol=symbol, tf=timeframe, error=str(exc)[:120]) \
                if hasattr(_log, "warning") else None

        # 3) Stale cache is better than nothing.
        if path.exists():
            self.last_source[symbol] = "stale_cache"
            return _normalize(pd.read_csv(path, index_col=0, parse_dates=True)).tail(bars)

        # 4) Last resort: synthetic, clearly flagged.
        if self.fallback_synthetic:
            self.last_source[symbol] = "synthetic_fallback"
            return synthetic_ohlcv(symbol, SyntheticConfig(bars=bars))
        raise RuntimeError(f"no data available for {symbol} {timeframe}")


class CCXTProvider(MarketDataProvider):
    """Crypto OHLCV via ccxt public endpoints (no API key required)."""

    def __init__(self, exchange: str = "binance"):
        super().__init__(synthetic=False)
        import ccxt  # optional dependency
        self.exchange = getattr(ccxt, exchange)({"enableRateLimit": True, "timeout": 15000})

    def get_ohlcv(self, symbol: str, timeframe: str = "1D", bars: int = 500) -> pd.DataFrame:
        tf = _CCXT_TF.get(timeframe, "1d")
        raw = self.exchange.fetch_ohlcv(symbol, tf, limit=bars)
        df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
        df.index = pd.to_datetime(df["ts"], unit="ms")
        return df.drop(columns=["ts"])


class YFinanceProvider(MarketDataProvider):
    """Equities/ETF OHLCV via yfinance (free, no account)."""

    def __init__(self):
        super().__init__(synthetic=False)
        import yfinance  # noqa: F401 — ensure installed

    def get_ohlcv(self, symbol: str, timeframe: str = "1D", bars: int = 500) -> pd.DataFrame:
        import yfinance as yf
        interval = _YF_INTERVAL.get(timeframe, "1d")
        # yfinance caps intraday history; ask for a generous period and trim.
        period = "60d" if interval.endswith("m") else "5y"
        df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = _normalize(df)
        if timeframe in _RESAMPLE and interval == "1d":
            df = resample_ohlcv(df, _RESAMPLE[timeframe])
        return df.tail(bars)


def make_provider(source: str = "auto", exchange: str = "binance", cache: bool = True) -> MarketDataProvider:
    """Factory: build a provider for the requested source, wrapped in caching.

    source: "synthetic" | "crypto" | "equities" | "auto"
    "auto" routes per-symbol at call time via AutoProvider.
    """
    if source == "synthetic":
        return MarketDataProvider(synthetic=True)
    if source == "crypto":
        inner: MarketDataProvider = CCXTProvider(exchange)
    elif source == "equities":
        inner = YFinanceProvider()
    else:
        inner = AutoProvider(exchange)
    return CachingProvider(inner) if cache else inner


class AutoProvider(MarketDataProvider):
    """Routes each symbol to crypto (ccxt) or equities (yfinance) on demand."""

    def __init__(self, exchange: str = "binance"):
        super().__init__(synthetic=False)
        self._exchange_name = exchange
        self._crypto: CCXTProvider | None = None
        self._equity: YFinanceProvider | None = None

    def _route(self, symbol: str) -> MarketDataProvider:
        if "/" in symbol:
            if self._crypto is None:
                self._crypto = CCXTProvider(self._exchange_name)
            return self._crypto
        if self._equity is None:
            self._equity = YFinanceProvider()
        return self._equity

    def get_ohlcv(self, symbol: str, timeframe: str = "1D", bars: int = 500) -> pd.DataFrame:
        return self._route(symbol).get_ohlcv(symbol, timeframe, bars)
