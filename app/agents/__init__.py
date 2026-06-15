"""Multi-agent layer.

Agents are grouped by responsibility:
  * Analytic  -> produce scores/votes (trend, momentum, volatility, regime, ...)
  * Decisional-> CIO, Risk, Portfolio (validate, allocate, veto)
  * Operational-> Execution, Audit (act, record)

Hard rule: no analytic agent can execute a trade. They propose; Risk + CIO
dispose. This separation is structural, not a convention.
"""

from app.agents.base import AnalyticAgent, vote_from_score
from app.agents.momentum_agent import MomentumAgent
from app.agents.quant_agent import QuantAgent
from app.agents.regime_agent import RegimeAgent
from app.agents.structure_agent import MarketStructureAgent
from app.agents.trend_agent import TrendAgent
from app.agents.volatility_agent import VolatilityAgent
from app.agents.volume_agent import VolumeAgent

DEFAULT_ANALYTIC_AGENTS: list[AnalyticAgent] = [
    TrendAgent(),
    MomentumAgent(),
    VolatilityAgent(),
    RegimeAgent(),
    VolumeAgent(),
    MarketStructureAgent(),
    QuantAgent(),
]

__all__ = [
    "AnalyticAgent",
    "vote_from_score",
    "TrendAgent",
    "MomentumAgent",
    "VolatilityAgent",
    "RegimeAgent",
    "VolumeAgent",
    "MarketStructureAgent",
    "QuantAgent",
    "DEFAULT_ANALYTIC_AGENTS",
]
