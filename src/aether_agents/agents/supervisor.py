"""Thin supervisor: Episode + Context → Attribution → Critic → Advisory.

Lean custom state graph (no heavy orchestration dependency). Accepts Pydantic
EpisodeOutput / ContextOutput even if sibling agents are still landing.
"""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, Field

from aether_agents.agents.advisory import AdvisoryAgent
from aether_agents.agents.attribution import AttributionAgent
from aether_agents.agents.critic import CriticAgent
from aether_agents.agents.evidence import (
    AdvisoryResult,
    AttributionResult,
    ContextOutput,
    CriticResult,
    EpisodeOutput,
    context_from_vector,
    episode_from_object,
)
from aether_agents.config import Settings, get_settings


class PipelineState(BaseModel):
    """Mutable graph state passed through Attribution → Critic → Advisory."""

    episode: EpisodeOutput
    context: ContextOutput
    attribution: AttributionResult | None = None
    critic: CriticResult | None = None
    advisory: AdvisoryResult | None = None
    errors: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


class PipelineResult(BaseModel):
    """Final supervisor output for API / dashboard consumers."""

    episode: EpisodeOutput
    context: ContextOutput
    attribution: AttributionResult
    critic: CriticResult
    advisory: AdvisoryResult
    graph: list[str] = Field(
        default_factory=lambda: ["attribution", "critic", "advisory"]
    )


NodeFn = Callable[[PipelineState], PipelineState]


class Supervisor:
    """Orchestrate attribution advisory chain with optional node hooks."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.attribution_agent = AttributionAgent(self.settings)
        self.critic_agent = CriticAgent(self.settings)
        self.advisory_agent = AdvisoryAgent(self.settings)

    def _node_attribution(self, state: PipelineState) -> PipelineState:
        state.attribution = self.attribution_agent.run(state.episode, state.context)
        return state

    def _node_critic(self, state: PipelineState) -> PipelineState:
        if state.attribution is None:
            raise RuntimeError("critic node requires attribution")
        state.critic = self.critic_agent.run(
            state.attribution, state.episode, state.context
        )
        return state

    def _node_advisory(self, state: PipelineState) -> PipelineState:
        if state.critic is None:
            raise RuntimeError("advisory node requires critic")
        state.advisory = self.advisory_agent.run(state.episode, state.critic)
        return state

    def graph_nodes(self) -> list[tuple[str, NodeFn]]:
        return [
            ("attribution", self._node_attribution),
            ("critic", self._node_critic),
            ("advisory", self._node_advisory),
        ]

    def run(self, episode: EpisodeOutput, context: ContextOutput) -> PipelineResult:
        state = PipelineState(episode=episode, context=context)
        for name, node in self.graph_nodes():
            try:
                state = node(state)
                state.meta.setdefault("completed_nodes", []).append(name)
            except Exception as exc:  # noqa: BLE001  # surface in state for API
                state.errors.append(f"{name}: {exc}")
                raise

        assert state.attribution is not None
        assert state.critic is not None
        assert state.advisory is not None
        return PipelineResult(
            episode=state.episode,
            context=state.context,
            attribution=state.attribution,
            critic=state.critic,
            advisory=state.advisory,
            graph=[name for name, _ in self.graph_nodes()],
        )


def run_attribution_pipeline(
    episode: EpisodeOutput | dict[str, Any] | Any,
    context: ContextOutput | dict[str, Any] | Any,
    settings: Settings | None = None,
) -> PipelineResult:
    """Coerce Episode/Context sibling outputs (or dicts) then run supervisor."""

    ep = episode_from_object(episode)
    ctx = context_from_vector(context)
    return Supervisor(settings=settings).run(ep, ctx)
