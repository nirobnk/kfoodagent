"""The provider wrapper. No network: this checks what gets built, not what it says."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from agent.llm import get_llm
from agent.tools import TOOLS
from config import settings


@pytest.fixture(autouse=True)
def fresh_cache():
    get_llm.cache_clear()
    yield
    get_llm.cache_clear()


def test_openrouter_points_at_openrouter(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr("sk-or-test"))

    llm = get_llm("openrouter", "google/gemini-3.1-flash-lite")

    assert llm.model_name == "google/gemini-3.1-flash-lite"
    assert str(llm.openai_api_base).rstrip("/") == "https://openrouter.ai/api/v1"
    # OpenRouter attributes traffic with these; without them the call still works.
    assert llm.default_headers["X-Title"] == settings.openrouter_app_name


def test_openrouter_model_can_be_swapped_by_env(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr("sk-or-test"))
    monkeypatch.setattr(settings, "llm_provider", "openrouter")
    monkeypatch.setattr(settings, "llm_model", "openai/gpt-4o-mini")

    assert get_llm().model_name == "openai/gpt-4o-mini"


def test_tools_bind_to_the_openrouter_model(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr("sk-or-test"))

    bound = get_llm("openrouter", "google/gemini-3.1-flash-lite").bind_tools(TOOLS)

    names = {tool["function"]["name"] for tool in bound.kwargs["tools"]}
    assert {"search_menu", "create_order", "store_info", "escalate_to_human"} <= names


def test_gemini_direct_still_works(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("gm-test"))

    llm = get_llm("gemini", "gemini-2.0-flash")

    assert "gemini-2.0-flash" in str(llm.model)


def test_an_unknown_provider_fails_loudly():
    with pytest.raises(ValueError, match="unsupported LLM_PROVIDER"):
        get_llm("deepthought", "42")


def test_the_api_key_follows_the_provider(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", SecretStr("sk-or-test"))
    assert settings.llm_api_key() == "sk-or-test"

    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("gm-test"))
    assert settings.llm_api_key() == "gm-test"
