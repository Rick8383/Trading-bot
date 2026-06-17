from app.core.config import apply_risk_profile, load_config
from app.data.market_data import MarketDataProvider
from app.data.providers import _CCXT_TF
from app.db.store import SQLiteStore
from app.execution.broker_factory import make_broker
from app.scheduler.loop import RealtimeRunner


def test_risk_profiles_scale_sizing_and_concurrency():
    base = load_config()
    low = apply_risk_profile(base, "low")
    high = apply_risk_profile(base, "high")
    assert low.risk.risk_per_trade < high.risk.risk_per_trade
    assert high.risk.risk_per_trade == 0.02
    assert high.risk.max_positions == 20
    # Hard invariant preserved: leverage stays 1.0 in every profile.
    assert high.risk.default_leverage == 1.0
    assert low.risk.default_leverage == 1.0


def test_unknown_profile_is_noop():
    base = load_config()
    same = apply_risk_profile(base, "nonexistent")
    assert same.risk.risk_per_trade == base.risk.risk_per_trade


def test_intraday_timeframes_mapped():
    for tf in ("1m", "5m", "15m", "30m", "1H", "4H", "1D"):
        assert tf in _CCXT_TF


def test_top20_crypto_universe_loaded():
    s = load_config()
    assert len(s.universe.crypto) == 20
    assert "BTC/USDT" in s.universe.crypto and "DOGE/USDT" in s.universe.crypto


def test_runner_intraday_timeframe_runs(tmp_path):
    s = apply_risk_profile(load_config(), "high")
    s.learning.store_path = str(tmp_path / "kb.json")
    s.learning.journal_path = str(tmp_path / "j.jsonl")
    runner = RealtimeRunner(
        settings=s, provider=MarketDataProvider(synthetic=True),
        broker=make_broker(s, "paper"), symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        store=SQLiteStore(tmp_path / "t.db"), base_timeframe="5m", context_timeframe="1H",
    )
    decisions = runner.run_once()
    assert len(decisions) == 3                 # synthetic provider serves any TF
    assert runner.base_timeframe == "5m"
