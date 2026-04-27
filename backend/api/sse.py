from __future__ import annotations

from .models import AgentStreamEvent


def to_sse_data(event: AgentStreamEvent) -> str:
    """Encode a strict JSON payload as an SSE data frame."""
    return f"data: {event.model_dump_json()}\n\n"
