"""Vote aggregation: collapse many AgentVotes into role scores + a net bias.

Each agent has a ``role`` (trend/momentum/...). Within a role we take a
confidence-weighted mean of scores. Across roles, the conviction engine applies
the configured weights. We also surface the aggregated directional bias and all
risk flags for the risk veto.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from app.models import AgentVote


@dataclass
class AggregatedVotes:
    role_scores: dict[str, float]            # role -> [-100,100]
    directional_bias: float                  # net [-100,100]
    risk_flags: list[str] = field(default_factory=list)
    confidence: float = 0.5
    per_agent: list[AgentVote] = field(default_factory=list)


def aggregate(votes: list[AgentVote]) -> AggregatedVotes:
    by_role: dict[str, list[AgentVote]] = defaultdict(list)
    for v in votes:
        role = v.features.get("role", "other")
        by_role[role].append(v)

    role_scores: dict[str, float] = {}
    for role, vs in by_role.items():
        wsum = sum(v.confidence for v in vs) or 1.0
        role_scores[role] = sum(v.score * v.confidence for v in vs) / wsum

    # Net directional bias = confidence-weighted mean across all agents.
    wsum = sum(v.confidence for v in votes) or 1.0
    bias = sum(v.score * v.confidence for v in votes) / wsum
    avg_conf = sum(v.confidence for v in votes) / (len(votes) or 1)

    flags = sorted({f for v in votes for f in v.risk_flags})
    return AggregatedVotes(role_scores, bias, flags, avg_conf, votes)
