"""Multi-agent layer.

Agents are grouped by responsibility:
  * Analytic  -> produce scores/votes (trend, momentum, volatility, regime, ...)
  * Decisional-> CIO, Risk, Portfolio (validate, allocate, veto)
  * Operational-> Execution, Audit (act, record)

Hard rule: no analytic agent can execute a trade. They propose; Risk + CIO
dispose. This separation is structural, not a convention.
"""

from app.agents.base import AnalyticAgent, vote_from_score
from app.agents.ml_agent import MLAgent
from app.agents.momentum_agent import MomentumAgent
from app.agents.quant_agent import QuantAgent
from app.agents.regime_agent import RegimeAgent
from app.agents.smc_agent import SMCAgent
from app.agents.structure_agent import MarketStructureAgent
from app.agents.trend_agent import TrendAgent
from app.agents.volatility_agent import VolatilityAgent
from app.agents.volume_agent import VolumeAgent

# SMC is cheap and deterministic -> on by default (low-weighted). ML trains a
# model each call, so it is opt-in via build_agents(include_ml=True).
DEFAULT_ANALYTIC_AGENTS: list[AnalyticAgent] = [
    TrendAgent(),
    MomentumAgent(),
    VolatilityAgent(),
    RegimeAgent(),
    VolumeAgent(),
    MarketStructureAgent(),
    QuantAgent(),
    SMCAgent(),
]


def build_agents(include_ml: bool = False, include_smc: bool = True) -> list[AnalyticAgent]:
    """Assemble the analytic agent roster.

    ML is advisory and comparatively expensive (trains per cycle), hence opt-in.
    """
    agents: list[AnalyticAgent] = [
        TrendAgent(), MomentumAgent(), VolatilityAgent(), RegimeAgent(),
        VolumeAgent(), MarketStructureAgent(), QuantAgent(),
    ]
    if include_smc:
        agents.append(SMCAgent())
    if include_ml:
        agents.append(MLAgent())
    return agents


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
    "SMCAgent",
    "MLAgent",
    "DEFAULT_ANALYTIC_AGENTS",
    "build_agents",
]
