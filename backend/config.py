"""Environment configuration, validated once at import time.

Every secret in this project is read here and nowhere else. If a required
variable is missing the process refuses to start, loudly, with the name of the
variable in the error message.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent
REPO_DIR = BACKEND_DIR.parent

# Absolute paths, so the process reads the same files wherever it is started
# from. The repo-root file is the shared one; backend/.env overrides it.
ENV_FILES = (REPO_DIR / ".env", BACKEND_DIR / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- WhatsApp Cloud API ---
    wa_access_token: str = Field(min_length=1)
    wa_phone_number_id: str = Field(min_length=1)
    wa_business_account_id: str = ""
    wa_verify_token: str = Field(min_length=8)
    wa_app_secret: str = ""
    wa_api_version: str = "v26.0"

    # --- Supabase ---
    # Current key names (sb_secret_… / sb_publishable_…). The legacy JWT keys
    # still work and are accepted as a fallback, but Supabase is retiring them.
    supabase_url: str = Field(min_length=1)
    supabase_secret_key: str = ""
    supabase_publishable_key: str = ""
    supabase_service_role_key: str = ""      # legacy
    supabase_anon_key: str = ""              # legacy
    supabase_jwks_url: str = ""              # asymmetric token verification
    supabase_jwt_secret: str = ""            # legacy HS256 secret

    # --- LLM ---
    llm_provider: Literal["openrouter", "gemini", "openai", "anthropic"] = "openrouter"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Optional attribution, shown on the OpenRouter activity page.
    openrouter_site_url: str = "https://kfoods.lk"
    openrouter_app_name: str = "K FOOD WhatsApp Agent"
    gemini_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    llm_model: str = "google/gemini-3.1-flash-lite"
    llm_temperature: float = 0.2
    llm_max_tool_loops: int = 6
    # A WhatsApp reply is a few hundred tokens. Left unset, providers reserve
    # credit against the model's full output ceiling (65k on Gemini Flash),
    # which fails with a 402 on a low balance before a single token is written.
    llm_max_tokens: int = 1024

    # --- App ---
    business_id: str = Field(min_length=1)
    auto_return_minutes: int = 30
    history_turns: int = 10
    notes_limit: int = 5
    log_level: str = "INFO"
    environment: Literal["development", "production"] = "development"
    cors_origins: str = "http://localhost:3000"
    send_rate_limit_per_minute: int = 30
    require_auth: bool = True

    @field_validator("wa_api_version")
    @classmethod
    def _version_prefix(cls, v: str) -> str:
        return v if v.startswith("v") else f"v{v}"

    @field_validator("supabase_url")
    @classmethod
    def _base_url(cls, v: str) -> str:
        """Keep only the project origin.

        The dashboard shows several URLs; pasting the REST one
        (https://<ref>.supabase.co/rest/v1/) makes every query 404, because the
        client appends /rest/v1 itself.
        """
        v = v.strip().rstrip("/")
        for suffix in ("/rest/v1", "/auth/v1", "/storage/v1", "/realtime/v1", "/functions/v1"):
            if v.endswith(suffix):
                v = v[: -len(suffix)]
        return v.rstrip("/")

    @model_validator(mode="after")
    def _require_a_server_key(self) -> "Settings":
        if not self.supabase_key:
            raise ValueError(
                "set SUPABASE_SECRET_KEY (sb_secret_…) or the legacy SUPABASE_SERVICE_ROLE_KEY"
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def supabase_key(self) -> str:
        """The server-side key. Bypasses RLS — backend only, never the browser."""
        return self.supabase_secret_key or self.supabase_service_role_key

    @property
    def supabase_client_key(self) -> str:
        """The browser-safe key, used here only to validate dashboard tokens."""
        return self.supabase_publishable_key or self.supabase_anon_key

    @property
    def uses_legacy_supabase_keys(self) -> bool:
        return not self.supabase_secret_key and bool(self.supabase_service_role_key)

    @property
    def graph_api_base(self) -> str:
        return f"https://graph.facebook.com/{self.wa_api_version}"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def llm_api_key(self) -> str:
        return {
            "openrouter": self.openrouter_api_key,
            "gemini": self.gemini_api_key,
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
        }[self.llm_provider]

    def check_production_readiness(self) -> list[str]:
        """Return a list of problems that must be fixed before going live."""
        problems: list[str] = []
        if not self.wa_app_secret:
            problems.append("WA_APP_SECRET is empty: webhook signatures are not verified.")
        if not self.require_auth:
            problems.append("REQUIRE_AUTH is false: the staff API is unauthenticated.")
        if not self.llm_api_key():
            problems.append(f"No API key set for LLM_PROVIDER={self.llm_provider}.")
        if not self.supabase_jwks_url and not self.supabase_jwt_secret and not self.supabase_client_key:
            problems.append(
                "None of SUPABASE_JWKS_URL, SUPABASE_JWT_SECRET or SUPABASE_PUBLISHABLE_KEY "
                "is set: dashboard tokens cannot be validated."
            )
        if "*" in self.cors_origin_list:
            problems.append("CORS_ORIGINS contains '*'.")
        return problems


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        missing = ", ".join(str(e["loc"][0]).upper() for e in exc.errors())
        print(
            f"\nFATAL: configuration is incomplete or invalid.\n"
            f"Check these environment variables: {missing}\n"
            f"See .env.example for the full list.\n\n{exc}\n",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


settings = get_settings()
