"""Multi-agent layer.

Agents are grouped by responsibility:
  * Analytic  -> produce scores/votes (trend, momentum, volatility, regime, ...)
  * Decisional-> CIO, Risk, Portfolio (validate, allocate, veto)
  * Operational-> Execution, Audit (act, record)

Hard rule: no analytic agent can execute a trade. They propose; Risk + CIO
dispose. This separation is structural, not a convention.
"""

from app.agents.base import AnalyticAgent, vote_from_score
from app.agents.macro_agent import MacroAgent
from app.agents.ml_agent import MLAgent
from app.agents.momentum_agent import MomentumAgent
from app.agents.news_agent import NewsAgent
from app.agents.quant_agent import QuantAgent
from app.agents.regime_agent import RegimeAgent
from app.agents.smc_agent import SMCAgent
from app.agents.social_agent import SocialSentimentAgent
from app.agents.structure_agent import MarketStructureAgent
from app.agents.trend_agent import TrendAgent
from app.agents.volatility_agent import VolatilityAgent
from app.agents.volume_agent import VolumeAgent
from app.agents.volume_profile_agent import VolumeProfileAgent

# SMC + Macro are cheap and deterministic -> on by default (low-weighted).
# Macro uses market breadth (injected by the pipeline). ML trains a model each
# call (opt-in). News/Social need external feeds (opt-in via include_external).
DEFAULT_ANALYTIC_AGENTS: list[AnalyticAgent] = [
    TrendAgent(),
    MomentumAgent(),
    VolatilityAgent(),
    RegimeAgent(),
    VolumeAgent(),
    MarketStructureAgent(),
    QuantAgent(),
    SMCAgent(),
    MacroAgent(),
    VolumeProfileAgent(),
]


def build_agents_from_settings(settings) -> list[AnalyticAgent]:
    """Build the roster from settings.layers — the per-layer on/off source."""
    L = settings.layers
    agents: list[AnalyticAgent] = [
        TrendAgent(), MomentumAgent(), VolatilityAgent(), RegimeAgent(),
        VolumeAgent(), MarketStructureAgent(), QuantAgent(),
    ]
    if L.smc:
        agents.append(SMCAgent())
    if L.macro:
        agents.append(MacroAgent())
    if L.volume_profile:
        agents.append(VolumeProfileAgent())
    if L.news:
        agents.append(NewsAgent())
    if L.social:
        agents.append(SocialSentimentAgent())
    if L.ml:
        agents.append(MLAgent())
    return agents


def build_agents(
    include_ml: bool = False,
    include_smc: bool = True,
    include_macro: bool = True,
    include_external: bool = False,
    include_volume_profile: bool = True,
) -> list[AnalyticAgent]:
    """Assemble the analytic agent roster.

    * ML is advisory and expensive (trains per cycle) -> opt-in.
    * News/Social need external feeds; without one they abstain, so they are
      opt-in via ``include_external`` to keep the default roster lean.
    """
    agents: list[AnalyticAgent] = [
        TrendAgent(), MomentumAgent(), VolatilityAgent(), RegimeAgent(),
        VolumeAgent(), MarketStructureAgent(), QuantAgent(),
    ]
    if include_smc:
        agents.append(SMCAgent())
    if include_macro:
        agents.append(MacroAgent())
    if include_volume_profile:
        agents.append(VolumeProfileAgent())
    if include_external:
        agents.extend([NewsAgent(), SocialSentimentAgent()])
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
    "MacroAgent",
    "VolumeProfileAgent",
    "NewsAgent",
    "SocialSentimentAgent",
    "MLAgent",
    "DEFAULT_ANALYTIC_AGENTS",
    "build_agents",
    "build_agents_from_settings",
]
