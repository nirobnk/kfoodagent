"""Environment configuration, validated once at import time.

Every secret in this project is read here and nowhere else. If a required
variable is missing the process refuses to start, loudly, with the name of the
variable in the error message.

Secrets are typed `SecretStr`, so printing, logging or a traceback that
includes a Settings object shows `SecretStr('**********')` rather than the
credential. Reading one is deliberate: `.get_secret_value()` at the point of
use. Values that are public by design — the Supabase publishable key ships to
every browser, ids and URLs are not credentials — stay plain strings.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent
REPO_DIR = BACKEND_DIR.parent

# Absolute paths, so the process reads the same files wherever it is started
# from. The repo-root file is the shared one; backend/.env overrides it.
ENV_FILES = (REPO_DIR / ".env", BACKEND_DIR / ".env")

Provider = Literal["openrouter", "gemini", "openai", "anthropic"]

# The model to use when LLM_MODEL is not set. Each provider names its models
# differently — an OpenRouter id carries a vendor prefix ("google/…") that the
# vendor's own API rejects — so a single shared default cannot serve all four.
# Keeping them here means switching provider is one env change, not two.
DEFAULT_MODELS: dict[str, str] = {
    "openrouter": "google/gemini-2.5-flash",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
    "anthropic": "claude-haiku-4-5-20251001",
}

# Suffixes the Supabase dashboard shows on URLs that are not the project origin.
_SUPABASE_PATH_SUFFIXES = ("/rest/v1", "/auth/v1", "/storage/v1", "/realtime/v1", "/functions/v1")


def _is_loopback(origin: str) -> bool:
    """A developer's own machine, where plain http is expected."""
    host = origin.split("://", 1)[-1].split(":", 1)[0]
    return host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def _secret(value: SecretStr | None) -> str:
    """Unwrap an optional secret to a plain string, empty when unset."""
    return value.get_secret_value() if value else ""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILES,
        env_file_encoding="utf-8",
        # The repo-root .env is shared with tooling that has its own variables
        # (NGROK_AUTHTOKEN and friends); they are not this application's to know.
        extra="ignore",
        case_sensitive=False,
    )

    # ---------------------------------------------------------------- WhatsApp
    wa_access_token: SecretStr = Field(min_length=1)
    wa_app_secret: SecretStr = SecretStr("")
    # Shared with Meta, echoed back on the subscription handshake.
    wa_verify_token: SecretStr = Field(min_length=8)
    # Identifiers, not credentials.
    wa_phone_number_id: str = Field(min_length=1)
    wa_business_account_id: str = ""
    wa_api_version: str = "v26.0"

    # ---------------------------------------------------------------- Supabase
    # Current key names are sb_secret_… / sb_publishable_…. The legacy JWT keys
    # still work and are read as a fallback, but Supabase is retiring them.
    supabase_url: str = Field(min_length=1)
    supabase_secret_key: SecretStr = SecretStr("")
    supabase_service_role_key: SecretStr = SecretStr("")   # legacy
    supabase_jwt_secret: SecretStr = SecretStr("")         # legacy HS256 secret
    # Browser-safe by design: these ship inside the dashboard bundle.
    supabase_publishable_key: str = ""
    supabase_anon_key: str = ""                            # legacy
    supabase_jwks_url: str = ""                            # asymmetric verification

    # --------------------------------------------------------------------- LLM
    llm_provider: Provider = "openrouter"
    openrouter_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    anthropic_api_key: SecretStr = SecretStr("")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Optional attribution, shown on the OpenRouter activity page.
    openrouter_site_url: str = "https://kfoods.lk"
    openrouter_app_name: str = "K FOOD WhatsApp Agent"
    # Blank means "whatever DEFAULT_MODELS says for the provider in use", so
    # LLM_PROVIDER can be changed on its own.
    llm_model: str = ""
    llm_temperature: float = 0.2
    llm_max_tool_loops: int = 6
    # Reasoning models only (gpt-5*, o-series); the older chat models reject the
    # parameter outright, so it is sent only when set. Valid values vary by
    # model. Critically, this agent always calls tools, and on gpt-5.6-* over
    # /v1/chat/completions anything other than "none" is refused with
    # "Function tools with reasoning_effort are not supported" — which would
    # fail every single customer message. See the check below.
    llm_reasoning_effort: Literal[
        "", "none", "minimal", "low", "medium", "high", "xhigh"
    ] = ""
    # A WhatsApp reply is a few hundred tokens. Left unset, providers reserve
    # credit against the model's full output ceiling (65k on Gemini Flash),
    # which fails with a 402 on a low balance before a single token is written.
    llm_max_tokens: int = 1024

    # ------------------------------------------------------------- Application
    business_id: str = Field(min_length=1)
    environment: Literal["development", "production"] = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"
    require_auth: bool = True
    send_rate_limit_per_minute: int = 30
    # Deliberately high. The failure mode that matters is a POS coming back from
    # a day offline with forty queued bills: throttling that into 429s would be
    # the limiter causing the outage the offline queue exists to survive.
    pos_rate_limit_per_minute: int = 120
    auto_return_minutes: int = 30
    history_turns: int = 10
    notes_limit: int = 5

    # -------------------------------------------------------------- validators
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
        for suffix in _SUPABASE_PATH_SUFFIXES:
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

    # ---------------------------------------------------------- derived values
    @property
    def supabase_key(self) -> str:
        """The server-side key. Bypasses RLS — backend only, never the browser."""
        return _secret(self.supabase_secret_key) or _secret(self.supabase_service_role_key)

    @property
    def supabase_client_key(self) -> str:
        """The browser-safe key, used here only to validate dashboard tokens."""
        return self.supabase_publishable_key or self.supabase_anon_key

    @property
    def uses_legacy_supabase_keys(self) -> bool:
        return not _secret(self.supabase_secret_key) and bool(
            _secret(self.supabase_service_role_key)
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def graph_api_base(self) -> str:
        return f"https://graph.facebook.com/{self.wa_api_version}"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def model(self) -> str:
        """The model id to send, honouring LLM_MODEL when it is set."""
        return self.llm_model or DEFAULT_MODELS[self.llm_provider]

    def api_key_for(self, provider: str) -> str:
        """The plain key for a provider. The only place that mapping lives."""
        return _secret(
            {
                "openrouter": self.openrouter_api_key,
                "gemini": self.gemini_api_key,
                "openai": self.openai_api_key,
                "anthropic": self.anthropic_api_key,
            }.get(provider)
        )

    def llm_api_key(self) -> str:
        """The key for the configured provider."""
        return self.api_key_for(self.llm_provider)

    def model_matches_provider(self) -> bool:
        """Catch the classic slip: switching provider but not the model id.

        OpenRouter routes by a "vendor/model" id; the vendors' own APIs reject
        that prefix and answer 404. Anything else is left alone, because model
        names change far faster than this file does.
        """
        prefixed = "/" in self.model
        return prefixed if self.llm_provider == "openrouter" else not prefixed

    # --------------------------------------------------------------- readiness
    def _security_problems(self) -> list[str]:
        """Anything that would expose the service if it went live as-is."""
        problems: list[str] = []
        if not _secret(self.wa_app_secret):
            problems.append("WA_APP_SECRET is empty: webhook signatures are not verified.")
        if not self.require_auth:
            problems.append("REQUIRE_AUTH is false: the staff API is unauthenticated.")
        if "*" in self.cors_origin_list:
            problems.append("CORS_ORIGINS contains '*'.")
        if not self.supabase_url.startswith("https://"):
            problems.append(f"SUPABASE_URL is not https: {self.supabase_url}")
        # A plain-http origin is a real risk anywhere; a local one is only a
        # problem once this is live, and warning about it in development just
        # teaches people to ignore warnings.
        insecure = [
            o
            for o in self.cors_origin_list
            if o.startswith("http://")
            and (self.is_production or not _is_loopback(o))
        ]
        if insecure:
            problems.append(f"CORS_ORIGINS allows plain http: {', '.join(insecure)}")
        if not self.supabase_jwks_url and not _secret(self.supabase_jwt_secret):
            if not self.supabase_client_key:
                problems.append(
                    "None of SUPABASE_JWKS_URL, SUPABASE_JWT_SECRET or "
                    "SUPABASE_PUBLISHABLE_KEY is set: dashboard tokens cannot be validated."
                )
        return problems

    def _configuration_problems(self) -> list[str]:
        """Settings that are wrong rather than unsafe — the service would fail."""
        problems: list[str] = []
        if not self.llm_api_key():
            problems.append(f"No API key set for LLM_PROVIDER={self.llm_provider}.")
        if self.llm_model and not self.model_matches_provider():
            problems.append(
                f"LLM_MODEL={self.llm_model!r} does not look like a "
                f"{self.llm_provider} model id. Only OpenRouter uses a "
                f'"vendor/model" prefix; clear LLM_MODEL to use the default '
                f"({DEFAULT_MODELS[self.llm_provider]})."
            )
        if self.llm_reasoning_effort not in ("", "none"):
            problems.append(
                f"LLM_REASONING_EFFORT={self.llm_reasoning_effort!r} with tool calling is "
                "refused by the gpt-5.6 models on /v1/chat/completions, which fails every "
                'reply. Use "none" unless you have confirmed this model accepts it.'
            )
        if self.uses_legacy_supabase_keys:
            problems.append(
                "Using the legacy SUPABASE_SERVICE_ROLE_KEY. Supabase is retiring it; "
                "move to SUPABASE_SECRET_KEY (sb_secret_…)."
            )
        return problems

    def check_production_readiness(self) -> list[str]:
        """Return a list of problems that must be fixed before going live."""
        return self._security_problems() + self._configuration_problems()


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
