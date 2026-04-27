from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections.abc import AsyncIterator, Mapping
from contextlib import suppress
from functools import lru_cache
from typing import Any, Final, cast

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    messages_from_dict,
)
from langgraph.graph.state import CompiledStateGraph

from db.checkpointing import ConversationPersistence, PersistenceError
from multi_agent.graph import build_two_agent_graph
from multi_agent.routing import build_router
from multi_agent.state import ActiveAgent, AgentName, ExecutionState

from .models import AgentRunRequest, AgentStreamEvent
from .sse import to_sse_data

try:
    from openai import (  # type: ignore
        APIConnectionError,
        APIError,
        APITimeoutError,
        InternalServerError,
        RateLimitError,
    )
except Exception:  # pragma: no cover - best-effort import
    APIConnectionError = None  # type: ignore[assignment]
    APIError = None  # type: ignore[assignment]
    APITimeoutError = None  # type: ignore[assignment]
    InternalServerError = None  # type: ignore[assignment]
    RateLimitError = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

PERSISTENCE = ConversationPersistence()
ROUTER = build_router(
    (AgentName.RESEARCHER, AgentName.CODER),
    progression=(AgentName.RESEARCHER.value, AgentName.CODER.value),
)

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

LLM_PROVIDER_EXCEPTIONS: tuple[type[BaseException], ...] = tuple(
    exc
    for exc in (
        APIConnectionError,
        APIError,
        InternalServerError,
        RateLimitError,
    )
    if exc is not None
)


class ClientDisconnectError(RuntimeError):
    """Raised when the SSE client disconnects mid-stream."""


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


def _to_json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _to_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_json_safe(item) for item in value]
    if isinstance(value, BaseMessage):
        return {
            "type": value.type,
            "content": _to_text(value.content),
        }
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


def _extract_run_id(event: Mapping[str, Any]) -> str:
    run_id = event.get("run_id")
    if isinstance(run_id, (str, int)):
        return str(run_id)

    fallback = event.get("id")
    if isinstance(fallback, (str, int)):
        return str(fallback)

    return str(uuid.uuid4())


def _extract_message_content(message: Any) -> str:
    if isinstance(message, BaseMessage):
        return _to_text(message.content)
    if isinstance(message, Mapping) and "content" in message:
        return _to_text(message["content"])
    return _to_text(message)


def _coerce_messages(raw_messages: Any) -> list[BaseMessage]:
    if not isinstance(raw_messages, list):
        return []

    parsed_messages: list[BaseMessage] = []
    for item in raw_messages:
        if isinstance(item, BaseMessage):
            parsed_messages.append(item)
            continue

        if isinstance(item, Mapping):
            if "type" in item and "data" in item:
                try:
                    hydrated = messages_from_dict([dict(item)])
                    parsed_messages.extend(hydrated)
                    continue
                except Exception:
                    pass

            if "content" in item:
                parsed_messages.append(AIMessage(content=_to_text(item["content"])))
                continue

        parsed_messages.append(AIMessage(content=_to_text(item)))

    return parsed_messages


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


def _extract_agent_output_update(
    event: Mapping[str, Any],
) -> tuple[str, Mapping[str, Any]] | None:
    agent_name = _resolve_agent_name(event)
    if agent_name not in KNOWN_AGENT_NAMES:
        return None

    data = event.get("data")
    if not isinstance(data, Mapping):
        return None

    output = data.get("output")
    if isinstance(output, Mapping):
        return (agent_name, output)

    return None


def _apply_node_output_to_state(
    state: ExecutionState,
    *,
    agent_name: str,
    output_update: Mapping[str, Any],
) -> tuple[ExecutionState, str | None, str]:
    merged_state: ExecutionState = {
        "messages": list(state["messages"]),
        "active_agent": cast(ActiveAgent, agent_name),
    }

    new_messages = _coerce_messages(output_update.get("messages"))
    if new_messages:
        merged_state["messages"].extend(new_messages)

    raw_output_text = ""
    if new_messages:
        raw_output_text = _extract_message_content(new_messages[-1])
    elif "content" in output_update:
        raw_output_text = _to_text(output_update.get("content"))

    output_content = _strip_routing_directive(raw_output_text)

    route_target = ROUTER(merged_state)
    if route_target == "FINISHED":
        return merged_state, None, output_content

    merged_state["active_agent"] = cast(ActiveAgent, route_target)
    return merged_state, route_target, output_content


def _build_initial_state(prompt: str) -> ExecutionState:
    return {
        "messages": [HumanMessage(content=prompt)],
        "active_agent": AgentName.RESEARCHER.value,
    }


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


def _format_provider_error(exc: BaseException) -> str:
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if status_code is None and response is not None:
        status_code = getattr(response, "status_code", None)
    detail = getattr(exc, "message", None) or str(exc)
    if status_code:
        return f"LLM provider error (HTTP {status_code}): {detail}"
    return f"LLM provider error: {detail}"


async def stream_agent_run(
    request: AgentRunRequest,
    client_request: Any | None = None,
) -> AsyncIterator[str]:
    """
    Stream LangGraph execution as strict JSON SSE frames.

    Each frame includes: agent_name, event_type, content.
    """
    graph = get_streaming_graph(
        model_name=request.model_name,
        temperature=round(request.temperature, 4),
        timeout_seconds=round(request.timeout_seconds, 2),
    )

    prompt = request.prompt.strip() if isinstance(request.prompt, str) else ""
    initial_state = _build_initial_state(prompt)
    requested_session_id = (
        str(request.session_id) if request.session_id is not None else None
    )

    try:
        bootstrap = PERSISTENCE.bootstrap_session(
            model_name=request.model_name,
            prompt=prompt if prompt else None,
            initial_state=initial_state,
            resume=request.resume,
            requested_session_id=requested_session_id,
        )
    except PersistenceError as exc:
        logger.warning("Session bootstrap failed: %s", exc)
        yield to_sse_data(
            AgentStreamEvent(
                agent_name="system",
                event_type="error",
                content=str(exc),
            )
        )
        return

    session_id = str(bootstrap.session_id)
    runtime_state = bootstrap.state
    turn_index = bootstrap.next_turn_index
    final_answer: tuple[str, str] | None = None

    yield to_sse_data(
        AgentStreamEvent(
            agent_name="system",
            event_type="thought",
            content=(
                f"SESSION_ID: {session_id} (resumed)"
                if bootstrap.resumed
                else f"SESSION_ID: {session_id}"
            ),
        )
    )

    event_queue: asyncio.Queue[Mapping[str, Any]] = asyncio.Queue()

    async def _produce_events() -> None:
        async with asyncio.timeout(request.timeout_seconds):
            async for event in graph.astream_events(runtime_state, version="v2"):
                await event_queue.put(event)

    producer_task = asyncio.create_task(_produce_events())

    try:
        while True:
            if client_request is not None:
                is_disconnected = await client_request.is_disconnected()
                if is_disconnected:
                    raise ClientDisconnectError(
                        "Client disconnected during SSE streaming."
                    )

            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=0.2)
            except asyncio.TimeoutError:
                if producer_task.done():
                    break
                continue

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

            if event_name == "on_tool_start":
                run_id = _extract_run_id(event)
                data = event.get("data")
                input_payload = (
                    {"input": _to_json_safe(data.get("input"))}
                    if isinstance(data, Mapping)
                    else None
                )

                PERSISTENCE.record_tool_start(
                    session_id=session_id,
                    run_id=run_id,
                    turn_index=turn_index,
                    agent_name=_resolve_agent_name(event),
                    tool_name=str(event.get("name", "tool")),
                    input_payload=cast(dict[str, Any] | None, input_payload),
                )

                yield to_sse_data(
                    AgentStreamEvent(
                        agent_name=_resolve_agent_name(event),
                        event_type="tool_execution",
                        content=_tool_event_content(event),
                    )
                )
                continue

            if event_name == "on_tool_end":
                run_id = _extract_run_id(event)
                data = event.get("data")
                output_payload = (
                    {"output": _to_json_safe(data.get("output"))}
                    if isinstance(data, Mapping)
                    else None
                )

                PERSISTENCE.record_tool_end(
                    session_id=session_id,
                    run_id=run_id,
                    output_payload=cast(dict[str, Any] | None, output_payload),
                    error_message=None,
                )

                yield to_sse_data(
                    AgentStreamEvent(
                        agent_name=_resolve_agent_name(event),
                        event_type="tool_execution",
                        content=_tool_event_content(event),
                    )
                )
                continue

            if event_name == "on_chain_end":
                update_candidate = _extract_agent_output_update(event)
                if update_candidate is not None:
                    agent_name, output_update = update_candidate
                    runtime_state, next_agent, output_content = (
                        _apply_node_output_to_state(
                            runtime_state,
                            agent_name=agent_name,
                            output_update=output_update,
                        )
                    )

                    persisted_output = output_content or _strip_routing_directive(
                        _to_text(output_update)
                    )
                    PERSISTENCE.save_turn_checkpoint(
                        session_id=session_id,
                        turn_index=turn_index,
                        agent_name=agent_name,
                        output_content=persisted_output,
                        next_agent=next_agent,
                        state=runtime_state,
                    )

                    if persisted_output:
                        final_answer = (agent_name, persisted_output)
                    turn_index += 1
                    continue

                candidate = _extract_agent_output_candidate(event)
                if candidate is not None:
                    final_answer = candidate

        if producer_task.done():
            producer_error = producer_task.exception()
            if producer_error is not None:
                raise producer_error

        PERSISTENCE.mark_session_completed(
            session_id=session_id, final_state=runtime_state
        )

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
    except ClientDisconnectError:
        PERSISTENCE.mark_session_paused(
            session_id=session_id,
            reason="Client disconnected before workflow completion.",
        )
        return
    except TIMEOUT_EXCEPTIONS as exc:
        logger.warning("LLM timeout while streaming workflow: %s", exc)
        PERSISTENCE.mark_session_paused(
            session_id=session_id,
            reason="LLM API timeout while executing the workflow.",
        )
        yield to_sse_data(
            AgentStreamEvent(
                agent_name="system",
                event_type="error",
                content="LLM API timeout while executing the workflow.",
            )
        )
    except LLM_PROVIDER_EXCEPTIONS as exc:
        logger.warning("LLM provider error while streaming workflow: %s", exc)
        error_message = _format_provider_error(exc)
        PERSISTENCE.mark_session_paused(
            session_id=session_id,
            reason=error_message,
        )
        yield to_sse_data(
            AgentStreamEvent(
                agent_name="system",
                event_type="error",
                content=error_message,
            )
        )
    except PersistenceError as exc:
        logger.exception("Persistence error while streaming workflow.")
        PERSISTENCE.mark_session_failed(session_id=session_id, error_message=str(exc))
        yield to_sse_data(
            AgentStreamEvent(
                agent_name="system",
                event_type="error",
                content=f"Persistence error: {exc}",
            )
        )
    except Exception:
        logger.exception("Unexpected error while streaming workflow.")
        PERSISTENCE.mark_session_failed(
            session_id=session_id,
            error_message="Unexpected server error while executing the workflow.",
        )
        yield to_sse_data(
            AgentStreamEvent(
                agent_name="system",
                event_type="error",
                content="Unexpected server error while executing the workflow.",
            )
        )
    finally:
        if not producer_task.done():
            producer_task.cancel()
            with suppress(asyncio.CancelledError):
                await producer_task
