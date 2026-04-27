from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentName(str, Enum):
    RESEARCHER = "researcher"
    CODER = "coder"
    QA_TESTER = "qa_tester"


ActiveAgent = Literal["researcher", "coder", "qa_tester"]
RouteTarget = Literal["researcher", "coder", "qa_tester", "FINISHED"]


class ExecutionState(TypedDict):
    """Shared state carried across the graph."""

    # add_messages appends new messages so full history is always retained.
    messages: Annotated[list[BaseMessage], add_messages]
    active_agent: ActiveAgent


class ExecutionUpdate(TypedDict, total=False):
    """Partial updates emitted by graph nodes."""

    messages: list[BaseMessage]
    active_agent: ActiveAgent
