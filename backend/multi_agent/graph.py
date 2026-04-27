from __future__ import annotations

from collections.abc import Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .llm import build_foundational_llm
from .nodes import AgentSpec, make_agent_node
from .routing import build_router
from .state import ActiveAgent, AgentName, ExecutionState, RouteTarget

RESEARCHER_PROMPT = """
You are the Researcher agent in a multi-agent software execution graph.
Your job is to gather information, break down unclear requirements,
surface assumptions, and provide implementation-ready context.

When details are insufficient, ask targeted follow-up questions or propose
what additional data is needed. When context is ready, hand off to the Coder.
""".strip()

CODER_PROMPT = """
You are the Coder agent in a multi-agent software execution graph.
Your job is to transform researched context into concrete implementation plans,
code-level decisions, and actionable development output.

If requirements are ambiguous or missing, send work back to the Researcher.
When implementation is complete, mark the task as finished.
""".strip()


def build_execution_graph(
    agent_specs: Sequence[AgentSpec],
    *,
    start_agent: ActiveAgent,
    progression: tuple[ActiveAgent, ...],
) -> CompiledStateGraph:
    """
    Build a modular execution graph.

    This is intentionally generic so you can add a QA Tester by:
    1) adding a QA `AgentSpec`,
    2) extending `progression` (for example: researcher -> coder -> qa_tester).
    """
    if not agent_specs:
        raise ValueError("agent_specs must contain at least one agent.")

    configured_agent_names = {spec.name.value for spec in agent_specs}
    if start_agent not in configured_agent_names:
        raise ValueError(f"start_agent '{start_agent}' is not present in agent_specs.")

    graph = StateGraph(ExecutionState)

    for spec in agent_specs:
        graph.add_node(spec.name.value, make_agent_node(spec))

    graph.add_edge(START, start_agent)

    router = build_router((spec.name for spec in agent_specs), progression=progression)
    route_map: dict[RouteTarget, str] = {
        spec.name.value: spec.name.value for spec in agent_specs
    }
    route_map["FINISHED"] = END

    for spec in agent_specs:
        graph.add_conditional_edges(spec.name.value, router, route_map)

    return graph.compile()


def build_two_agent_graph(
    *,
    llm: BaseChatModel | None = None,
    model_name: str = "gpt-4o-mini",
    temperature: float = 0.1,
) -> CompiledStateGraph:
    """Build the default Researcher <-> Coder graph."""
    shared_llm = llm or build_foundational_llm(
        model_name=model_name, temperature=temperature
    )

    specs = (
        AgentSpec(
            name=AgentName.RESEARCHER,
            system_prompt=RESEARCHER_PROMPT,
            llm=shared_llm,
        ),
        AgentSpec(
            name=AgentName.CODER,
            system_prompt=CODER_PROMPT,
            llm=shared_llm,
        ),
    )

    return build_execution_graph(
        specs,
        start_agent=AgentName.RESEARCHER.value,
        progression=(AgentName.RESEARCHER.value, AgentName.CODER.value),
    )
