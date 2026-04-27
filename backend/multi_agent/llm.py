from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI


def build_foundational_llm(
    *,
    model_name: str = "gpt-4o-mini",
    temperature: float = 0.1,
    streaming: bool = False,
    request_timeout_seconds: float | None = None,
    max_retries: int = 2,
) -> BaseChatModel:
    """Create the shared foundational model used by all agents."""
    llm_kwargs: dict[str, Any] = {
        "model": model_name,
        "temperature": temperature,
        "streaming": streaming,
        "max_retries": max_retries,
    }

    if request_timeout_seconds is not None:
        llm_kwargs["timeout"] = request_timeout_seconds

    return ChatOpenAI(**llm_kwargs)
