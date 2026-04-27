from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EventType = Literal["thought", "tool_execution", "final_answer", "error"]


class AgentRunRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)
    model_name: str = Field(default="gpt-4o-mini", min_length=1)
    temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    timeout_seconds: float = Field(default=120.0, gt=1.0, le=600.0)


class AgentStreamEvent(BaseModel):
    """Strict SSE payload structure sent to the frontend."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(min_length=1)
    event_type: EventType
    content: str
