import numpy as np
import pandas as pd

from app.core.config import PortfolioConfig
from app.data import indicators as ind
from app.data.market_data import trending_ohlcv
from app.decision.portfolio import (
    assess_candidate,
    avg_correlation,
    correlation_matrix,
    correlation_scale,
    effective_bets,
)


def _corr_from_series(series: dict[str, list[float]]) -> pd.DataFrame:
    daily = {}
    for k, closes in series.items():
        n = len(closes)
        daily[k] = pd.DataFrame({
            "open": closes, "high": closes, "low": closes, "close": closes,
            "volume": [1.0] * n,
        })
    return correlation_matrix(daily, lookback=n - 2)


def test_correlation_matrix_detects_comovement():
    base = list(np.cumsum(np.random.default_rng(1).normal(0, 1, 80)) + 100)
    same = [x + 0.01 for x in base]                 # near-identical path
    opp = list(200 - np.array(base))                # inverse path
    corr = _corr_from_series({"A": base, "B": same, "C": opp})
    assert corr.at["A", "B"] > 0.9
    assert corr.at["A", "C"] < -0.9


def test_correlation_scale_shrinks_with_correlation():
    cfg = PortfolioConfig()
    assert correlation_scale(0.1, cfg) == 1.0              # below threshold
    mid = correlation_scale(0.6, cfg)
    high = correlation_scale(0.95, cfg)
    assert cfg.min_scale <= high < mid < 1.0


def test_assess_candidate_vetoes_highly_correlated():
    base = list(np.cumsum(np.random.default_rng(2).normal(0, 1, 80)) + 100)
    same = [x + 0.01 for x in base]
    corr = _corr_from_series({"A": base, "B": same})
    cfg = PortfolioConfig(max_correlation=0.85)
    veto, scale, _ = assess_candidate("A", ["B"], corr, cfg)
    assert veto is True and scale == 0.0


def test_assess_candidate_passes_when_uncorrelated():
    rng = np.random.default_rng(3)
    a = list(np.cumsum(rng.normal(0, 1, 80)) + 100)
    b = list(np.cumsum(rng.normal(0, 1, 80)) + 100)   # independent
    corr = _corr_from_series({"A": a, "B": b})
    veto, scale, _ = assess_candidate("A", ["B"], corr, PortfolioConfig())
    assert veto is False and 0 < scale <= 1.0


def test_no_constraint_without_holdings():
    veto, scale, _ = assess_candidate("A", [], pd.DataFrame(), PortfolioConfig())
    assert veto is False and scale == 1.0


def test_effective_bets_lower_when_correlated():
    base = list(np.cumsum(np.random.default_rng(4).normal(0, 1, 80)) + 100)
    same = [x + 0.01 for x in base]
    rng = np.random.default_rng(5)
    indep = list(np.cumsum(rng.normal(0, 1, 80)) + 100)
    corr_crowded = _corr_from_series({"A": base, "B": same})
    corr_diverse = _corr_from_series({"A": base, "B": indep})
    w = {"A": 0.5, "B": 0.5}
    assert effective_bets(w, corr_crowded) < effective_bets(w, corr_diverse)
