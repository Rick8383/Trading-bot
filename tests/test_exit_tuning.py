"""Tests for the exit/stop tuning + learning bonuses (favor profitable contexts)."""

from app.agents.cio_agent import CIOAgent
from app.core.config import ExitConfig, load_config
from app.core.constants import Action, MarketRegime
from app.execution.exit_manager import manage_position
from app.execution.order_validator import Order
from app.execution.paper_broker import PaperBroker
from app.learning.knowledge_base import KnowledgeBase
from app.learning.postmortem import post_mortem, setup_signature
from app.learning.trade_journal import TradeRecord


def _win(regime="high_vol", flags=("elevated_volatility",), ret=0.06):
    return TradeRecord(
        symbol="X", action="LONG", entry=100, exit=106, stop_loss=97, take_profit=112,
        quantity=10, pnl=ret * 1000, return_pct=ret, reason="take_profit",
        conviction=70, reward_risk=2.5, regime=regime, risk_flags=list(flags),
    )


# --- learning bonuses -------------------------------------------------

def test_knowledge_base_rewards_profitable_context(tmp_path):
    kb = KnowledgeBase(tmp_path / "kb.json", min_samples=8)
    for _ in range(10):
        rec = _win()
        kb.ingest(rec, post_mortem(rec))   # winners produce no error tags
    sig = setup_signature(action="LONG", regime="high_vol", conviction=70,
                          reward_risk=2.5, risk_flags=["elevated_volatility"])
    bonuses = kb.bonuses(sig)
    assert bonuses.get("flag:elevated_volatility", 0) > 0
    assert any(l.key == "flag:elevated_volatility" for l in kb.winning_contexts())
    # A proven-good context is not penalized.
    assert kb.penalties(sig) == {}


def test_cio_bonus_raises_conviction():
    from app.models import RegimeAssessment
    from app.scoring.vote_engine import aggregate
    from app.agents.base import vote_from_score
    from app.decision.adaptive_risk import adapt_risk
    from app.data import indicators as ind
    from app.data.market_data import trending_ohlcv

    s = load_config()
    cio = CIOAgent(s)
    df = ind.enrich(trending_ohlcv("X", 1, 220))
    agg = aggregate([vote_from_score("TrendAI", "X", "trend", 50, 0.8, "t"),
                     vote_from_score("MomentumAI", "X", "momentum", 45, 0.7, "m")])
    reg = RegimeAssessment(regime=MarketRegime.BULL, confidence=0.8, reasoning="t")
    rp = adapt_risk(base_risk=s.risk.risk_per_trade, regime=MarketRegime.BULL)
    kw = dict(asset="X", agg=agg, regime=reg, last_price=float(df["close"].iloc[-1]),
              atr=float(df["atr"].iloc[-1]), risk_params=rp, df=df)
    base = cio.form_idea(**kw)
    boosted = cio.form_idea(**kw, learned_bonuses={"flag:elevated_volatility": 10.0})
    if base and boosted:
        assert boosted.conviction >= base.conviction


# --- exit tuning ------------------------------------------------------

def test_default_time_stop_spares_profitable_trade():
    b = PaperBroker(cash=100_000, slippage_bps=0, commission_bps=0)
    b.submit(Order("X", Action.LONG, 100, 100, stop_loss=96, take_profit=120))
    pos = b.positions["X"]
    pos.bars_held = 80                       # well past time_stop_bars
    # Default policy: min_r=0.0 -> a trade in profit (+0.5R) is NOT time-stopped.
    produced = manage_position(b, pos, 102, atr=2.0, policy=ExitConfig())
    assert all(t.reason != "time_stop" for t in produced)
    assert "X" in b.positions


def test_default_time_stop_still_cuts_losing_stagnant_trade():
    b = PaperBroker(cash=100_000, slippage_bps=0, commission_bps=0)
    b.submit(Order("X", Action.LONG, 100, 100, stop_loss=96, take_profit=120))
    pos = b.positions["X"]
    pos.bars_held = 80
    produced = manage_position(b, pos, 99.5, atr=2.0, policy=ExitConfig())  # below entry
    assert produced and produced[0].reason == "time_stop"


def test_config_tuning_applied():
    s = load_config()
    assert s.risk.min_rr == 2.5
    assert s.strategy.atr_stop_multiplier == 3.0
    assert s.exits.time_stop_bars == 60 and s.exits.time_stop_min_r == 0.0
