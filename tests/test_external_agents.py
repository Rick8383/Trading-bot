from app.agents import build_agents
from app.agents.cio_agent import CIOAgent
from app.agents.macro_agent import MacroAgent
from app.agents.news_agent import NewsAgent
from app.agents.social_agent import SocialSentimentAgent
from app.data import indicators as ind
from app.data.external import NeutralProvider, StaticProvider
from app.data.market_data import trending_ohlcv
from app.orchestration.pipeline import DecisionPipeline, PortfolioState
from app.risk.risk_manager import RiskManager


def _frames(symbols, direction=1):
    out = {}
    for s in symbols:
        df = ind.enrich(trending_ohlcv(s, direction=direction, bars=320))
        out[s] = {tf: df for tf in ("1D", "1W")}
    return out


def _data_with_ctx(ctx):
    df = ind.enrich(trending_ohlcv("X", 1, 200))
    return {"1D": df, "_context": ctx}


# --- agents abstain without a feed ------------------------------------

def test_macro_neutral_without_breadth():
    v = MacroAgent().analyze("X", _data_with_ctx({}))
    assert v.score == 0.0 and v.confidence <= 0.3


def test_macro_reads_injected_breadth():
    v = MacroAgent().analyze("X", _data_with_ctx({"macro_score": 60.0, "breadth": 0.8}))
    assert v.score == 60.0
    assert "Risk-On" in v.reasoning


def test_news_abstains_then_reads_feed():
    assert NewsAgent().analyze("X", _data_with_ctx({})).score == 0.0
    v = NewsAgent().analyze("X", _data_with_ctx({"news": {"X": -60.0}}))
    assert v.score == -60.0 and "adverse_news" in v.risk_flags


def test_social_contrarian_damping_at_extremes():
    euph = SocialSentimentAgent().analyze("X", _data_with_ctx({"sentiment": {"X": 90.0}}))
    assert "euphoria" in euph.risk_flags
    assert euph.score < 90.0          # bullishness tempered near euphoria
    panic = SocialSentimentAgent().analyze("X", _data_with_ctx({"sentiment": {"X": -90.0}}))
    assert "panic" in panic.risk_flags
    assert panic.score > -90.0        # bearishness tempered near capitulation


# --- providers --------------------------------------------------------

def test_static_provider_returns_injected_scores():
    p = StaticProvider({"BTC/USDT": 70.0}, confidence=0.6)
    s, c, _ = p.score("BTC/USDT")
    assert s == 70.0 and c == 0.6
    assert p.score("UNKNOWN")[0] == 0.0      # default
    assert NeutralProvider().score("X")[0] == 0.0


# --- pipeline integration ---------------------------------------------

def test_pipeline_injects_breadth_and_feeds(settings):
    pipe = DecisionPipeline(
        settings=settings, agents=build_agents(include_external=True),
        risk_manager=RiskManager(settings.risk), cio=CIOAgent(settings),
        news_provider=StaticProvider({"AAA": 80.0}, name="news"),
        sentiment_provider=StaticProvider({"AAA": -85.0}, name="social"),
    )
    decisions = pipe.run_cycle(_frames(["AAA", "BBB", "CCC", "DDD"], direction=1), PortfolioState(positions=[]))
    assert len(decisions) == 4
    # MacroAI participates by default; News/Social present with include_external.
    consulted = set(decisions[0].consulted_agents)
    assert "MacroAI" in consulted and "NewsAI" in consulted and "SocialSentimentAI" in consulted


def test_build_agents_external_flags():
    roles = {a.role for a in build_agents(include_external=True)}
    assert {"macro", "news", "sentiment"} <= roles
    assert "news" not in {a.role for a in build_agents(include_external=False)}
