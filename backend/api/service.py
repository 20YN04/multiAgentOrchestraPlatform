from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Mapping
from functools import lru_cache
from typing import Any, Final

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph

from multi_agent.graph import build_two_agent_graph
from multi_agent.state import AgentName, ExecutionState

from .models import AgentRunRequest, AgentStreamEvent
from .sse import to_sse_data

try:
    from openai import APITimeoutError  # type: ignore
except Exception:  # pragma: no cover - best-effort import
    APITimeoutError = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

KNOWN_AGENT_NAMES: Final[frozenset[str]] = frozenset(
    {
        AgentName.RESEARCHER.value,
        AgentName.CODER.value,
        AgentName.QA_TESTER.value,
    }
)

ROUTING_DIRECTIVE_RE = re.compile(r"^\s*NEXT\s*:\s*[A-Z_]+\s*$", re.IGNORECASE)

TIMEOUT_EXCEPTIONS: tuple[type[BaseException], ...] = (
    asyncio.TimeoutError,
    TimeoutError,
)
if APITimeoutError is not None:
    TIMEOUT_EXCEPTIONS = TIMEOUT_EXCEPTIONS + (APITimeoutError,)


@lru_cache(maxsize=8)
def get_streaming_graph(
    model_name: str,
    temperature: float,
    timeout_seconds: float,
) -> CompiledStateGraph:
    """Build and cache a streaming-enabled graph for SSE usage."""
    return build_two_agent_graph(
        model_name=model_name,
        temperature=temperature,
        streaming=True,
        request_timeout_seconds=timeout_seconds,
    )


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        chunks: list[str] = []
        for item in value:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, Mapping):
                if "text" in item:
                    chunks.append(_to_text(item["text"]))
                elif "content" in item:
                    chunks.append(_to_text(item["content"]))
                else:
                    chunks.append(str(item))
            else:
                chunks.append(str(item))
        return "".join(chunks)
    return str(value)


def _resolve_agent_name(event: Mapping[str, Any]) -> str:
    metadata = event.get("metadata")
    if isinstance(metadata, Mapping):
        node_name = metadata.get("langgraph_node")
        if isinstance(node_name, str) and node_name in KNOWN_AGENT_NAMES:
            return node_name

    event_name = event.get("name")
    if isinstance(event_name, str) and event_name in KNOWN_AGENT_NAMES:
        return event_name

    return "system"


def _extract_streamed_token(event: Mapping[str, Any]) -> str:
    data = event.get("data")
    if not isinstance(data, Mapping):
        return ""

    chunk = data.get("chunk")
    if isinstance(chunk, BaseMessage):
        return _to_text(chunk.content)
    if isinstance(chunk, Mapping) and "content" in chunk:
        return _to_text(chunk["content"])

    content = getattr(chunk, "content", None)
    return _to_text(content)


def _extract_message_content(message: Any) -> str:
    if isinstance(message, BaseMessage):
        return _to_text(message.content)
    if isinstance(message, Mapping) and "content" in message:
        return _to_text(message["content"])
    return _to_text(message)


def _strip_routing_directive(text: str) -> str:
    cleaned_lines = [
        line for line in text.splitlines() if not ROUTING_DIRECTIVE_RE.match(line)
    ]
    return "\n".join(cleaned_lines).strip()


def _extract_agent_output_candidate(
    event: Mapping[str, Any],
) -> tuple[str, str] | None:
    agent_name = _resolve_agent_name(event)
    if agent_name not in KNOWN_AGENT_NAMES:
        return None

    data = event.get("data")
    if not isinstance(data, Mapping):
        return None

    output = data.get("output")
    if isinstance(output, Mapping):
        messages = output.get("messages")
        if isinstance(messages, list) and messages:
            candidate = _strip_routing_directive(_extract_message_content(messages[-1]))
            if candidate:
                return (agent_name, candidate)

    text_candidate = _strip_routing_directive(_to_text(output))
    if text_candidate:
        return (agent_name, text_candidate)

    return None


def _tool_event_content(event: Mapping[str, Any]) -> str:
    event_name = str(event.get("event", ""))
    tool_name = str(event.get("name", "tool"))
    data = event.get("data")

    if not isinstance(data, Mapping):
        return f"{tool_name} emitted {event_name}."

    if event_name == "on_tool_start":
        return f"{tool_name} started with input: {_to_text(data.get('input'))}"
    if event_name == "on_tool_end":
        return f"{tool_name} completed with output: {_to_text(data.get('output'))}"

    return f"{tool_name} emitted {event_name}."


async def stream_agent_run(request: AgentRunRequest) -> AsyncIterator[str]:
    """
    Stream LangGraph execution as strict JSON SSE frames.

    Each frame includes: agent_name, event_type, content.
    """
    graph = get_streaming_graph(
        model_name=request.model_name,
        temperature=round(request.temperature, 4),
        timeout_seconds=round(request.timeout_seconds, 2),
    )

    initial_state: ExecutionState = {
        "messages": [HumanMessage(content=request.prompt)],
        "active_agent": AgentName.RESEARCHER.value,
    }

    final_answer: tuple[str, str] | None = None

    try:
        async with asyncio.timeout(request.timeout_seconds):
            async for event in graph.astream_events(initial_state, version="v2"):
                event_name = str(event.get("event", ""))

                if event_name == "on_chat_model_stream":
                    token = _extract_streamed_token(event)
                    if token:
                        yield to_sse_data(
                            AgentStreamEvent(
                                agent_name=_resolve_agent_name(event),
                                event_type="thought",
                                content=token,
                            )
                        )
                    continue

                if event_name in {"on_tool_start", "on_tool_end"}:
                    yield to_sse_data(
                        AgentStreamEvent(
                            agent_name=_resolve_agent_name(event),
                            event_type="tool_execution",
                            content=_tool_event_content(event),
                        )
                    )
                    continue

                if event_name == "on_chain_end":
                    candidate = _extract_agent_output_candidate(event)
                    if candidate is not None:
                        final_answer = candidate

        if final_answer is not None:
            yield to_sse_data(
                AgentStreamEvent(
                    agent_name=final_answer[0],
                    event_type="final_answer",
                    content=final_answer[1],
                )
            )
        else:
            yield to_sse_data(
                AgentStreamEvent(
                    agent_name="system",
                    event_type="final_answer",
                    content="Workflow completed.",
                )
            )
    except TIMEOUT_EXCEPTIONS as exc:
        logger.warning("LLM timeout while streaming workflow: %s", exc)
        yield to_sse_data(
            AgentStreamEvent(
                agent_name="system",
                event_type="error",
                content="LLM API timeout while executing the workflow.",
            )
        )
    except Exception:
        logger.exception("Unexpected error while streaming workflow.")
        yield to_sse_data(
            AgentStreamEvent(
                agent_name="system",
                event_type="error",
                content="Unexpected server error while executing the workflow.",
            )
        )
