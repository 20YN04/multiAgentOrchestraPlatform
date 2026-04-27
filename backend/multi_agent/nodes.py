from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, cast

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from .state import ActiveAgent, AgentName, ExecutionState, ExecutionUpdate

ROUTING_DIRECTIVE_INSTRUCTION = """
At the very end of your response, include exactly one control line:
NEXT: RESEARCHER
or
NEXT: CODER
or
NEXT: FINISHED
""".strip()


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """Configuration needed to build one graph node for one agent."""

    name: AgentName
    system_prompt: str
    llm: BaseChatModel


AgentNode = Callable[[ExecutionState], ExecutionUpdate]


def _to_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(item) for item in content)
    return str(content)


def make_agent_node(spec: AgentSpec) -> AgentNode:
    """Create a typed LangGraph node function for an agent."""
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", spec.system_prompt.strip()),
            ("system", ROUTING_DIRECTIVE_INSTRUCTION),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )
    chain = prompt | spec.llm
    active_agent = cast(ActiveAgent, spec.name.value)

    def _node(state: ExecutionState) -> ExecutionUpdate:
        response = chain.invoke({"messages": state["messages"]})
        content = _to_text(
            response.content if isinstance(response, BaseMessage) else response
        )

        return {
            "messages": [AIMessage(content=content, name=spec.name.value)],
            "active_agent": active_agent,
        }

    return _node
