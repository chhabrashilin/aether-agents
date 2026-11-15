"""Agent package: Attribution, Critic, Advisory, and thin supervisor."""

from aether_agents.agents.advisory import AdvisoryAgent, build_advisory
from aether_agents.agents.attribution import AttributionAgent, attribute_episode
from aether_agents.agents.critic import CriticAgent, critique_attribution
from aether_agents.agents.evidence import (
    AdvisoryResult,
    AttributionResult,
    ContextOutput,
    CriticResult,
    EpisodeOutput,
    EvidenceFeature,
    SourceClass,
)
from aether_agents.agents.supervisor import PipelineResult, Supervisor, run_attribution_pipeline

__all__ = [
    "AdvisoryAgent",
    "AdvisoryResult",
    "AttributionAgent",
    "AttributionResult",
    "ContextOutput",
    "CriticAgent",
    "CriticResult",
    "EpisodeOutput",
    "EvidenceFeature",
    "PipelineResult",
    "SourceClass",
    "Supervisor",
    "attribute_episode",
    "build_advisory",
    "critique_attribution",
    "run_attribution_pipeline",
]
