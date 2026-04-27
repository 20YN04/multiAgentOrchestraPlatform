from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI


def build_foundational_llm(
    *,
    model_name: str = "gpt-4o-mini",
    temperature: float = 0.1,
) -> BaseChatModel:
    """Create the shared foundational model used by all agents."""
    return ChatOpenAI(model=model_name, temperature=temperature)
