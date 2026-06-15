"""Market data sourcing.

Phase 1 ships a deterministic *synthetic* generator so the whole system can be
tested and demoed offline, plus a thin provider interface ready to back with
ccxt (crypto) or yfinance (equities/ETF) in Phase 3. Real connectors are
intentionally optional imports — the core never hard-depends on them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class SyntheticConfig:
    bars: int = 500
    start_price: float = 100.0
    drift: float = 0.0005          # per-bar expected log return
    volatility: float = 0.02       # per-bar log-return std
    seed: int | None = 42


def synthetic_ohlcv(symbol: str, cfg: SyntheticConfig | None = None) -> pd.DataFrame:
    """Generate a reproducible OHLCV frame via geometric Brownian motion.

    Deterministic given (symbol, seed): we mix the symbol into the seed so
    different assets get different — but repeatable — paths.
    """
    cfg = cfg or SyntheticConfig()
    seed = None if cfg.seed is None else (cfg.seed + (abs(hash(symbol)) % 100000))
    rng = np.random.default_rng(seed)

    log_ret = rng.normal(cfg.drift, cfg.volatility, cfg.bars)
    close = cfg.start_price * np.exp(np.cumsum(log_ret))
    # Build plausible OHLC around the close path.
    intrabar = np.abs(rng.normal(0, cfg.volatility, cfg.bars)) * close
    high = close + intrabar
    low = close - intrabar
    open_ = np.empty(cfg.bars)
    open_[0] = cfg.start_price
    open_[1:] = close[:-1]
    low = np.minimum.reduce([low, open_, close])
    high = np.maximum.reduce([high, open_, close])
    volume = rng.lognormal(mean=12, sigma=0.4, size=cfg.bars)

    idx = pd.date_range(end=pd.Timestamp.utcnow().normalize(), periods=cfg.bars, freq="D")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def trending_ohlcv(symbol: str, direction: int = 1, bars: int = 300) -> pd.DataFrame:
    """Helper for tests: a cleanly up- or down-trending series."""
    cfg = SyntheticConfig(bars=bars, drift=0.004 * direction, volatility=0.012, seed=7)
    return synthetic_ohlcv(symbol, cfg)


class MarketDataProvider:
    """Provider interface. Default implementation is synthetic + offline.

    Swap in a ccxt/yfinance-backed subclass later without touching callers.
    """

    def __init__(self, synthetic: bool = True):
        self.synthetic = synthetic

    def get_ohlcv(self, symbol: str, timeframe: str = "1D", bars: int = 500) -> pd.DataFrame:
        if self.synthetic:
            return synthetic_ohlcv(symbol, SyntheticConfig(bars=bars))
        raise NotImplementedError(
            "Live data connectors (ccxt/yfinance) are a Phase 3 deliverable; "
            "install the optional deps and subclass MarketDataProvider."
        )

    def get_multi_timeframe(
        self, symbol: str, timeframes: list[str], bars: int = 500
    ) -> dict[str, pd.DataFrame]:
        return {tf: self.get_ohlcv(symbol, tf, bars) for tf in timeframes}
