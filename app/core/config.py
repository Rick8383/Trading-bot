"""Typed, validated configuration loaded from ``config.yaml``.

Pydantic gives us fail-fast validation: a typo in a risk limit raises at
startup instead of silently mis-sizing positions in production.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from app.core.exceptions import ConfigError

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config.yaml"


class CapitalConfig(BaseModel):
    initial: float = Field(gt=0)
    currency: str = "USD"


class RiskConfig(BaseModel):
    risk_per_trade: float = Field(gt=0, le=0.05)
    risk_per_trade_min: float = Field(gt=0, le=0.05)
    risk_per_trade_max: float = Field(gt=0, le=0.05)
    daily_loss_limit: float = Field(gt=0, le=0.2)
    max_drawdown: float = Field(gt=0, le=0.5)
    min_rr: float = Field(ge=1.0)
    max_positions: int = Field(gt=0)
    max_asset_exposure: float = Field(gt=0, le=1.0)
    max_sector_exposure: float = Field(gt=0, le=1.0)
    max_gross_exposure: float = Field(gt=0, le=3.0)
    max_net_exposure: float = Field(gt=0, le=2.0)
    max_short_exposure: float = Field(ge=0, le=1.0)
    default_leverage: float = Field(ge=1.0, le=1.0)  # leverage forbidden by default

    @field_validator("risk_per_trade")
    @classmethod
    def _within_band(cls, v: float, info) -> float:
        # risk_per_trade must sit inside [min, max]
        lo = info.data.get("risk_per_trade_min", v)
        hi = info.data.get("risk_per_trade_max", v)
        if not (lo <= v <= hi):
            raise ValueError(f"risk_per_trade {v} outside [{lo}, {hi}]")
        return v


class DrawdownRung(BaseModel):
    dd: float = Field(ge=0, le=1.0)
    exposure: float = Field(ge=0, le=1.0)


class ConvictionConfig(BaseModel):
    flat_below: float = 40
    reduced_below: float = 60
    standard_below: float = 80


class StrategyConfig(BaseModel):
    rebalance: str = "daily"
    timeframes: list[str] = ["1H", "4H", "1D", "1W"]
    ema_periods: list[int] = [20, 50, 100, 200]
    atr_period: int = 14
    atr_stop_multiplier: float = 2.5
    adx_period: int = 14
    rsi_period: int = 14
    structure_stops: bool = True   # place SL/TP at support/resistance (ATR-bounded)
    ml_win_prob_weight: float = Field(default=0.5, ge=0, le=1)  # blend ML prob into EV


class CioWeights(BaseModel):
    risk: float = 0.25
    trend: float = 0.20
    momentum: float = 0.15
    regime: float = 0.10
    quant: float = 0.10
    macro: float = 0.10
    other: float = 0.10


class ExecutionConfig(BaseModel):
    slippage_bps: float = 5
    commission_bps: float = 2
    cost_aware: bool = True          # require EV to clear round-trip costs + buffer
    min_edge_pct: float = 0.10       # net EV must exceed costs by at least this (%)


class EntryConfig(BaseModel):
    """Entry timing. 'pullback' uses a limit order at the zone when price is
    extended; 'market' enters immediately at the current price."""

    enabled: bool = True
    mode: str = "pullback"            # pullback | market
    max_extension_atr: float = 1.5    # 'extended' if price > EMA20 + N*ATR (long)
    pullback_buffer_atr: float = 0.1  # limit sits this far above the EMA20 zone
    expiry_bars: int = 5              # cancel the limit if unfilled after N bars


class ExitConfig(BaseModel):
    """Active trade management. All thresholds are in R (risk) multiples."""

    enabled: bool = True
    scale_out_at_r: float = 1.0       # take partial profit at +1R
    scale_out_fraction: float = 0.5   # close half at the first target
    breakeven_at_r: float = 1.0       # move stop to entry once +1R is reached
    trail_after_r: float = 1.0        # start trailing once beyond +1R
    trail_atr_mult: float = 2.5
    time_stop_bars: int = 25          # cut a stagnating trade after N bars
    time_stop_min_r: float = 0.5      # ...if it has not reached this much R


class PortfolioConfig(BaseModel):
    """Correlation-aware portfolio construction.

    Stops a basket of highly-correlated names (e.g. 20 cryptos) from becoming
    one concentrated bet: a new trade too correlated with what's held is vetoed,
    and otherwise its size is shrunk by its average correlation to the book.
    """

    enabled: bool = True
    max_correlation: float = Field(default=0.85, ge=0, le=1)  # veto above this
    corr_lookback: int = 60
    min_scale: float = Field(default=0.4, ge=0, le=1)         # floor on size shrink
    corr_threshold: float = Field(default=0.3, ge=0, le=1)    # below: no shrink


class UniverseFilters(BaseModel):
    min_daily_volume: float = 0
    max_spread_bps: float = 100


class UniverseConfig(BaseModel):
    etfs: list[str] = []
    equities: list[str] = []
    crypto: list[str] = []
    filters: UniverseFilters = UniverseFilters()

    def all_symbols(self) -> list[str]:
        return [*self.etfs, *self.equities, *self.crypto]


class LearningConfig(BaseModel):
    enabled: bool = True
    min_samples_for_lesson: int = 8
    max_conviction_penalty: float = 25
    store_path: str = "data_store/knowledge.json"
    journal_path: str = "data_store/journal.jsonl"


class MonitoringConfig(BaseModel):
    telegram_enabled: bool = False
    email_enabled: bool = False
    prometheus_enabled: bool = False


class Settings(BaseModel):
    mode: str = "paper"
    capital: CapitalConfig
    risk: RiskConfig
    drawdown_ladder: list[DrawdownRung] = []
    conviction: ConvictionConfig = ConvictionConfig()
    strategy: StrategyConfig = StrategyConfig()
    cio_weights: CioWeights = CioWeights()
    execution: ExecutionConfig = ExecutionConfig()
    entries: EntryConfig = EntryConfig()
    exits: ExitConfig = ExitConfig()
    portfolio: PortfolioConfig = PortfolioConfig()
    universe: UniverseConfig = UniverseConfig()
    learning: LearningConfig = LearningConfig()
    monitoring: MonitoringConfig = MonitoringConfig()

    @field_validator("mode")
    @classmethod
    def _known_mode(cls, v: str) -> str:
        if v not in {"paper", "backtest", "live"}:
            raise ValueError(f"unknown mode: {v}")
        return v

    @property
    def live_unlocked(self) -> bool:
        """Live trading is gated behind an explicit env unlock token."""
        return os.getenv("LIVE_TRADING_UNLOCK") == "I_UNDERSTAND_THE_RISK"


def load_config(path: str | os.PathLike | None = None) -> Settings:
    """Load and validate configuration from YAML."""
    p = Path(path) if path else _DEFAULT_PATH
    if not p.exists():
        raise ConfigError(f"config file not found: {p}")
    try:
        raw = yaml.safe_load(p.read_text()) or {}
        return Settings(**raw)
    except Exception as exc:  # noqa: BLE001 - re-raise as domain error
        raise ConfigError(f"invalid configuration: {exc}") from exc


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide cached settings (override via load_config in tests)."""
    return load_config()


# Risk profiles: scale per-trade risk and concurrency. Hard invariants stay —
# stops mandatory, kill switch, no leverage, no martingale. "High" is genuinely
# higher risk, not reckless: it sizes more per trade and holds more names.
_RISK_PROFILES = {
    "low":    {"risk_per_trade": 0.005, "max_positions": 8,  "max_asset_exposure": 0.08},
    "medium": {"risk_per_trade": 0.010, "max_positions": 12, "max_asset_exposure": 0.10},
    "high":   {"risk_per_trade": 0.020, "max_positions": 20, "max_asset_exposure": 0.12},
}


def apply_risk_profile(settings: Settings, profile: str) -> Settings:
    """Return settings tuned to a risk profile (low | medium | high).

    Leverage stays at 1.0 and every guardrail remains; only sizing and the
    number of concurrent positions change.
    """
    p = _RISK_PROFILES.get(profile)
    if not p:
        return settings
    s = settings.model_copy(deep=True)
    s.risk.risk_per_trade = p["risk_per_trade"]
    s.risk.risk_per_trade_max = max(s.risk.risk_per_trade_max, p["risk_per_trade"])
    s.risk.risk_per_trade_min = min(s.risk.risk_per_trade_min, p["risk_per_trade"])
    s.risk.max_positions = p["max_positions"]
    s.risk.max_asset_exposure = p["max_asset_exposure"]
    return s
