from app.core.constants import Action, MarketRegime
from app.db.store import SQLiteStore
from app.learning.knowledge_base import KnowledgeBase
from app.learning.postmortem import post_mortem
from app.learning.trade_journal import TradeRecord
from app.models import FinalDecision


def _decision():
    return FinalDecision(
        asset="BTC/USDT", action=Action.LONG, conviction=72, allocation=0.08,
        quantity=1.2, entry=100, stop_loss=96, take_profit=110, expected_value=1.4,
        reward_risk=2.5, regime=MarketRegime.BULL, consulted_agents=["TrendAI", "CIO_AI"],
        risk_flags=["rsi_extreme"], learned_penalties={"low_conviction": 3.0},
    )


def _trade(ret=-0.03):
    return TradeRecord(
        symbol="BTC/USDT", action="LONG", entry=100, exit=97, stop_loss=96, take_profit=110,
        quantity=1.2, pnl=ret * 120, return_pct=ret, reason="stop_loss", conviction=72,
        reward_risk=2.5, regime="bear", risk_flags=["rsi_extreme"], error_tags=["x"],
    )


def test_store_persists_decisions_and_trades(tmp_path):
    store = SQLiteStore(tmp_path / "t.db")
    store.save_decision(_decision())
    store.save_trade(_trade())
    assert store.count("decisions") == 1
    assert store.count("trades") == 1
    recent = store.recent_trades(5)
    assert recent[0]["symbol"] == "BTC/USDT"


def test_store_upserts_lessons(tmp_path):
    store = SQLiteStore(tmp_path / "t.db")
    kb = KnowledgeBase(tmp_path / "kb.json", min_samples=4)
    for _ in range(6):
        rec = _trade()
        kb.ingest(rec, post_mortem(rec))
    store.upsert_lessons(kb.lessons)
    n1 = store.count("lessons")
    assert n1 > 0
    # Upserting again must not duplicate rows (ON CONFLICT(key)).
    store.upsert_lessons(kb.lessons)
    assert store.count("lessons") == n1


def test_store_survives_reopen(tmp_path):
    path = tmp_path / "t.db"
    SQLiteStore(path).save_trade(_trade())
    reopened = SQLiteStore(path)
    assert reopened.count("trades") == 1
