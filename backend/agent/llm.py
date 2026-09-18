"""One wrapper around the chat model, so the provider can be swapped in env.

Nothing else in the agent knows which provider is in use. Switching is a
single env change — LLM_PROVIDER — because config.DEFAULT_MODELS supplies a
matching model id per provider and LLM_MODEL only overrides it when set.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from config import settings

log = logging.getLogger(__name__)

# Only langchain-openai and langchain-google-genai are installed by default;
# the rest are optional extras. Without this, choosing an uninstalled provider
# fails with a bare ModuleNotFoundError that names the import, not the fix.
PROVIDER_PACKAGES = {
    "openrouter": "langchain-openai",
    "openai": "langchain-openai",
    "gemini": "langchain-google-genai",
    "anthropic": "langchain-anthropic",
}


def _missing(provider: str) -> ImportError:
    """The caller raises this `from` the original ImportError."""
    package = PROVIDER_PACKAGES.get(provider, "the provider package")
    return ImportError(
        f"LLM_PROVIDER={provider} needs {package}. "
        f"Add it to backend/requirements.txt and reinstall."
    )


@lru_cache(maxsize=4)
def get_llm(provider: str | None = None, model: str | None = None) -> Any:
    """Build the chat model. Swapping provider or model is an env change."""
    provider = provider or settings.llm_provider
    model = model or settings.model

    if provider == "openrouter":
        # OpenRouter speaks the OpenAI API, so the OpenAI client talks to it
        # with a different base URL. `model` is a routed id like
        # "google/gemini-3.1-flash-lite" — it must support tool calling, or the
        # agent cannot look up prices.
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise _missing("openrouter") from exc

        return ChatOpenAI(
            model=model,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            max_retries=2,
            default_headers={
                "HTTP-Referer": settings.openrouter_site_url,
                "X-Title": settings.openrouter_app_name,
            },
        )

    if provider == "gemini":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise _missing("gemini") from exc

        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.gemini_api_key,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            max_retries=2,
        )

    if provider == "openai":
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise _missing("openai") from exc

        return ChatOpenAI(
            model=model,
            api_key=settings.openai_api_key,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            max_retries=2,
        )

    if provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:
            raise _missing("anthropic") from exc

        return ChatAnthropic(
            model=model,
            api_key=settings.anthropic_api_key,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            max_retries=2,
        )

    raise ValueError(f"unsupported LLM_PROVIDER: {provider}")
