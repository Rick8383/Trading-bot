from app.agents import DEFAULT_ANALYTIC_AGENTS
from app.agents.trend_agent import TrendAgent
from app.core.constants import MarketRegime, Vote
from app.data import indicators as ind
from app.data.market_data import trending_ohlcv
from app.strategies.regime import classify_regime


def _frames(symbol, direction):
    df = ind.enrich(trending_ohlcv(symbol, direction=direction, bars=300))
    return {tf: df for tf in ("1H", "4H", "1D", "1W")}


def test_trend_agent_bullish_on_uptrend():
    vote = TrendAgent().analyze("UP", _frames("UP", 1))
    assert vote.score > 0
    assert vote.direction == Vote.BUY


def test_trend_agent_bearish_on_downtrend():
    vote = TrendAgent().analyze("DOWN", _frames("DOWN", -1))
    assert vote.score < 0
    assert vote.direction == Vote.SELL


def test_all_agents_produce_valid_votes():
    frames = _frames("UP", 1)
    for agent in DEFAULT_ANALYTIC_AGENTS:
        v = agent.analyze("UP", frames)
        assert -100 <= v.score <= 100
        assert 0 <= v.confidence <= 1
        assert abs(v.buy + v.sell + v.hold - 1.0) < 1e-6
        assert "role" in v.features


def test_regime_classifier_detects_uptrend():
    df = trending_ohlcv("UP", direction=1, bars=300)
    assessment = classify_regime(df)
    assert assessment.regime in (MarketRegime.BULL, MarketRegime.RECOVERY, MarketRegime.SIDEWAYS)
    assert 0 <= assessment.confidence <= 1
