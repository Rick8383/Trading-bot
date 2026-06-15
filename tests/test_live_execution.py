import pytest

from app.core.constants import Action
from app.core.exceptions import LiveTradingLocked, OrderRejected
from app.execution.broker_factory import make_broker
from app.execution.live_broker import AlpacaPaperBroker
from app.execution.order_validator import Order
from app.execution.paper_broker import PaperBroker


# --- factory safety ---------------------------------------------------

def test_factory_defaults_to_paper(settings):
    assert isinstance(make_broker(settings, "paper"), PaperBroker)


def test_factory_live_requires_unlock(settings, monkeypatch):
    monkeypatch.delenv("LIVE_TRADING_UNLOCK", raising=False)
    # No unlock -> falls back to in-process paper broker even if venue=alpaca.
    assert isinstance(make_broker(settings, "alpaca"), PaperBroker)


def test_factory_live_without_keys_falls_back(settings, monkeypatch):
    monkeypatch.setenv("LIVE_TRADING_UNLOCK", "I_UNDERSTAND_THE_RISK")
    monkeypatch.delenv("ALPACA_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET", raising=False)
    settings.__dict__.pop("live_unlocked", None)
    assert isinstance(make_broker(settings, "alpaca"), PaperBroker)


# --- Alpaca adapter (mocked transport) --------------------------------

class _FakeResp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._p


class _FakeClient:
    def __init__(self):
        self.posted = []

    def post(self, path, json):
        self.posted.append((path, json))
        return _FakeResp({"id": "order-1", "status": "accepted"})

    def get(self, path):
        return _FakeResp({"equity": "100000"})

    def delete(self, path):
        return _FakeResp({"status": "closed"})


def test_alpaca_locked_without_unlock():
    with pytest.raises(LiveTradingLocked):
        AlpacaPaperBroker("k", "s", unlocked=False)


def test_alpaca_submit_builds_bracket_with_stop():
    client = _FakeClient()
    b = AlpacaPaperBroker("k", "s", client=client, unlocked=True)
    order = Order("AAPL", Action.LONG, 10, 100, stop_loss=95, take_profit=110)
    res = b.submit(order)
    assert res["status"] == "accepted"
    path, payload = client.posted[0]
    assert path == "/v2/orders"
    assert payload["order_class"] == "bracket"
    assert payload["stop_loss"]["stop_price"] == 95
    assert b.equity() == 100000.0


def test_alpaca_refuses_stopless_order():
    b = AlpacaPaperBroker("k", "s", client=_FakeClient(), unlocked=True)
    with pytest.raises(OrderRejected):
        b.submit(Order("AAPL", Action.LONG, 10, 100, stop_loss=None))


# --- realtime loop ----------------------------------------------------

def test_realtime_run_once_executes_cycle(settings, tmp_path):
    from app.data.market_data import MarketDataProvider
    from app.db.store import SQLiteStore
    from app.scheduler.loop import RealtimeRunner

    settings.learning.store_path = str(tmp_path / "kb.json")
    settings.learning.journal_path = str(tmp_path / "j.jsonl")
    broker = make_broker(settings, "paper")
    runner = RealtimeRunner(
        settings=settings, provider=MarketDataProvider(synthetic=True),
        broker=broker, symbols=["AAA", "BBB", "CCC"], store=SQLiteStore(tmp_path / "t.db"),
    )
    decisions = runner.run_once()
    assert isinstance(decisions, list)
    assert len(decisions) == 3            # one decision per symbol
    assert runner.store.count("decisions") == 3
    # Running again must not raise (idempotent re: already-open positions).
    runner.run_once()
