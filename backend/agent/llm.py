"""One wrapper around the chat model, so the provider can be swapped in env."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from config import settings

log = logging.getLogger(__name__)


@lru_cache(maxsize=4)
def get_llm(provider: str | None = None, model: str | None = None) -> Any:
    """Build the chat model. Swapping provider or model is an env change."""
    provider = provider or settings.llm_provider
    model = model or settings.llm_model

    if provider == "openrouter":
        # OpenRouter speaks the OpenAI API, so the OpenAI client talks to it
        # with a different base URL. `model` is a routed id like
        # "google/gemini-3.1-flash-lite" — it must support tool calling, or the
        # agent cannot look up prices.
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            temperature=settings.llm_temperature,
            max_retries=2,
            default_headers={
                "HTTP-Referer": settings.openrouter_site_url,
                "X-Title": settings.openrouter_app_name,
            },
        )

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.gemini_api_key,
            temperature=settings.llm_temperature,
            max_retries=2,
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI  # requires langchain-openai

        return ChatOpenAI(
            model=model,
            api_key=settings.openai_api_key,
            temperature=settings.llm_temperature,
            max_retries=2,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic  # requires langchain-anthropic

        return ChatAnthropic(
            model=model,
            api_key=settings.anthropic_api_key,
            temperature=settings.llm_temperature,
            max_retries=2,
        )

    raise ValueError(f"unsupported LLM_PROVIDER: {provider}")
