from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, cast

from langchain_core.messages import AIMessage, BaseMessage

from .state import ActiveAgent, AgentName, ExecutionState, RouteTarget

DIRECTIVE_PATTERN = re.compile(r"^\s*NEXT\s*:\s*([A-Z_]+)\s*$", re.IGNORECASE | re.MULTILINE)


def _to_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(item) for item in content)
    return str(content)


def _last_assistant_message(messages: list[BaseMessage]) -> AIMessage | None:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return message
    return None


def _extract_directive(text: str) -> str | None:
    matches = DIRECTIVE_PATTERN.findall(text)
    if not matches:
        return None
    return matches[-1].upper()


@dataclass(frozen=True, slots=True)
class Router:
    """Routes execution based on the latest output directive."""

    available_agents: frozenset[ActiveAgent]
    progression: tuple[ActiveAgent, ...] = (
        AgentName.RESEARCHER.value,
        AgentName.CODER.value,
    )

    def __call__(self, state: ExecutionState) -> RouteTarget:
        last_message = _last_assistant_message(state["messages"])
        if last_message is not None:
            directive = _extract_directive(_to_text(last_message.content))
            if directive == "FINISHED":
                return "FINISHED"
            if directive is not None:
                candidate = directive.lower()
                if candidate in self.available_agents:
                    return cast(RouteTarget, candidate)

        return self._fallback_from_progression(state["active_agent"])

    def _fallback_from_progression(self, active_agent: ActiveAgent) -> RouteTarget:
        if active_agent in self.progression:
            current_index = self.progression.index(active_agent)
            for candidate in self.progression[current_index + 1 :]:
                if candidate in self.available_agents:
                    return cast(RouteTarget, candidate)

        return "FINISHED"


def build_router(
    agent_names: Iterable[AgentName],
    *,
    progression: tuple[ActiveAgent, ...] = (
        AgentName.RESEARCHER.value,
        AgentName.CODER.value,
    ),
) -> Router:
    available_agents = frozenset(cast(ActiveAgent, name.value) for name in agent_names)
    return Router(available_agents=available_agents, progression=progression)