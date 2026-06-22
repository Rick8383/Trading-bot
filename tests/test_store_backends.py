import pytest

from app.db import SQLiteStore, make_store
from app.monitoring.kill_switch import KillSwitch
from app.monitoring.metrics import compute_report
from app.monitoring.prometheus import render_prometheus


def test_make_store_defaults_to_sqlite(tmp_path):
    s = make_store(str(tmp_path / "x.db"))
    assert isinstance(s, SQLiteStore)
    assert make_store(f"sqlite:///{tmp_path/'y.db'}").__class__ is SQLiteStore


def test_make_store_routes_postgres_url(monkeypatch):
    # Routes to PostgresStore; without psycopg installed it raises a clear error.
    import app.db as dbmod

    called = {}

    class _Fake:
        def __init__(self, dsn):
            called["dsn"] = dsn

    monkeypatch.setattr("app.db.postgres_store.PostgresStore", _Fake, raising=True)
    store = make_store("postgresql://user:pw@localhost:5432/trading")
    assert called["dsn"].startswith("postgresql://")
    assert isinstance(store, _Fake)


def test_prometheus_exposition_format(tmp_path):
    store = SQLiteStore(tmp_path / "t.db")
    report = compute_report([100000, 101000, 100500], [0.01, -0.005])
    store.save_metric(100500, 0.005, report)
    text = render_prometheus(store, KillSwitch())
    assert "# TYPE tradingbot_equity gauge" in text
    assert "tradingbot_equity 100500" in text
    assert "tradingbot_kill_switch_active 0" in text


def test_prometheus_handles_empty_store():
    text = render_prometheus(None, KillSwitch())
    assert "tradingbot_kill_switch_active" in text  # still renders kill switch
