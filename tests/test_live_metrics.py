from app.core.config import load_config
from app.data.market_data import MarketDataProvider
from app.db.store import SQLiteStore
from app.execution.broker_factory import make_broker
from app.scheduler.loop import RealtimeRunner


def test_runner_persists_metric_snapshots(tmp_path):
    s = load_config()
    s.learning.store_path = str(tmp_path / "kb.json")
    s.learning.journal_path = str(tmp_path / "j.jsonl")
    store = SQLiteStore(tmp_path / "t.db")
    runner = RealtimeRunner(
        settings=s, provider=MarketDataProvider(synthetic=True),
        broker=make_broker(s, "paper"), symbols=["A", "B", "C"], store=store,
    )
    runner.run_once()
    runner.run_once()
    # The live loop must record an equity snapshot each cycle (dashboard source).
    assert store.count("metrics") == 2
    latest = store.latest_metric()
    assert latest["equity"] > 0
