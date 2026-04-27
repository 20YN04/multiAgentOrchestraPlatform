from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from langchain_core.messages import BaseMessage, messages_from_dict, messages_to_dict

from multi_agent.state import ActiveAgent, ExecutionState


def serialize_state(state: ExecutionState) -> dict[str, Any]:
    return {
        "messages": messages_to_dict(state["messages"]),
        "active_agent": state["active_agent"],
    }


def deserialize_state(payload: Mapping[str, Any]) -> ExecutionState:
    raw_messages = payload.get("messages")
    if not isinstance(raw_messages, list):
        raise ValueError("Serialized state is missing a valid 'messages' list.")

    raw_active_agent = payload.get("active_agent")
    if not isinstance(raw_active_agent, str):
        raise ValueError("Serialized state is missing a valid 'active_agent' field.")

    messages = cast(list[BaseMessage], messages_from_dict(raw_messages))
    active_agent = cast(ActiveAgent, raw_active_agent)
    return {
        "messages": messages,
        "active_agent": active_agent,
    }
