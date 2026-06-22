import tempfile
from pathlib import Path

from app.agents import DEFAULT_ANALYTIC_AGENTS
from app.agents.cio_agent import CIOAgent
from app.core.constants import Action
from app.data import indicators as ind
from app.data.market_data import trending_ohlcv
from app.learning.knowledge_base import KnowledgeBase
from app.orchestration.pipeline import DecisionPipeline, PortfolioState
from app.risk.risk_manager import RiskManager


def _frames(symbols, direction):
    out = {}
    for s in symbols:
        df = ind.enrich(trending_ohlcv(s, direction=direction, bars=320))
        out[s] = {tf: df for tf in ("1H", "4H", "1D", "1W")}
    return out


def _pipeline(settings, kb=None):
    return DecisionPipeline(
        settings=settings,
        agents=DEFAULT_ANALYTIC_AGENTS,
        risk_manager=RiskManager(settings.risk),
        cio=CIOAgent(settings),
        knowledge_base=kb,
    )


def test_pipeline_produces_decisions(settings):
    frames = _frames(["AAA", "BBB"], direction=1)
    state = PortfolioState(positions=[])
    decisions = _pipeline(settings).run_cycle(frames, state)
    assert len(decisions) == 2
    for d in decisions:
        assert d.action in (Action.LONG, Action.SHORT, Action.FLAT)
        # Every executed decision must carry a stop (cardinal rule).
        if not d.rejected and d.action != Action.FLAT:
            assert d.stop_loss is not None and d.entry is not None


def test_pipeline_flat_in_kill_drawdown(settings):
    frames = _frames(["AAA"], direction=1)
    state = PortfolioState(positions=[], drawdown=0.20)  # beyond kill threshold
    decisions = _pipeline(settings).run_cycle(frames, state)
    assert all(d.rejected or d.action == Action.FLAT for d in decisions)


def test_learned_penalty_lowers_conviction(settings):
    with tempfile.TemporaryDirectory() as d:
        kb = KnowledgeBase(Path(d) / "kb.json", min_samples=4)
        frames = _frames(["AAA"], direction=1)
        state = PortfolioState(positions=[])

        base = _pipeline(settings, kb).run_cycle(frames, state)[0]

        # Inject a confirmed-bad lesson matching this setup's flags/regime.
        from app.learning.postmortem import post_mortem
        from app.learning.trade_journal import TradeRecord
        regime = base.regime.value if base.regime else "bull"
        action = base.action.value if base.action != Action.FLAT else "LONG"
        for _ in range(8):
            rec = TradeRecord(
                symbol="AAA", action=action, entry=100, exit=97, stop_loss=96, take_profit=110,
                quantity=10, pnl=-30, return_pct=-0.03, reason="stop_loss",
                conviction=50, reward_risk=2.5, regime=regime, risk_flags=[],
            )
            kb.ingest(rec, post_mortem(rec))

        after = _pipeline(settings, kb).run_cycle(frames, state)[0]
        # If low_conviction was the matched lesson, conviction should not rise.
        assert after.conviction <= base.conviction + 1e-6
