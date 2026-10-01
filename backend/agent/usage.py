"""What each agent turn cost in tokens, and in dollars.

OpenAI bills four kinds of token at four prices, and on Sept 30 the dearest
kind — cache writes — was 82% of the bill. So all four are kept apart rather
than summed into one "tokens" figure that would hide where the money goes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from config import settings


@dataclass(slots=True)
class TokenUsage:
    model: str | None = None
    calls: int = 0
    input_tokens: int = 0          # everything sent, all four kinds together
    cached_tokens: int = 0         # read back from the cache: cheapest
    cache_write_tokens: int = 0    # new to the cache: dearest
    output_tokens: int = 0

    @property
    def uncached_tokens(self) -> int:
        return max(0, self.input_tokens - self.cached_tokens - self.cache_write_tokens)

    def add(self, message: Any) -> None:
        """Count one model reply. A provider that reports nothing adds nothing."""
        metadata = getattr(message, "response_metadata", None) or {}
        raw = metadata.get("token_usage") or {}
        details = raw.get("prompt_tokens_details") or {}
        usage = getattr(message, "usage_metadata", None) or {}
        cache = usage.get("input_token_details") or {}

        self.calls += 1
        self.model = metadata.get("model_name") or self.model
        self.input_tokens += int(raw.get("prompt_tokens") or usage.get("input_tokens") or 0)
        self.output_tokens += int(raw.get("completion_tokens") or usage.get("output_tokens") or 0)
        self.cached_tokens += int(details.get("cached_tokens") or cache.get("cache_read") or 0)
        self.cache_write_tokens += int(
            details.get("cache_write_tokens") or cache.get("cache_creation") or 0
        )

    def cost_usd(self) -> float:
        per_token = 1 / 1_000_000
        return round(
            (
                self.uncached_tokens * settings.llm_price_input
                + self.cached_tokens * settings.llm_price_cached_input
                + self.cache_write_tokens * settings.llm_price_cache_write
                + self.output_tokens * settings.llm_price_output
            )
            * per_token,
            6,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"cost_usd": self.cost_usd()}
