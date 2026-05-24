"""
Anthropic LLM client with tier routing. All calls go through this module so that
Langfuse tracing, retry logic (tenacity), and model selection live in one place.
Routing rule: Haiku 4.5 for classification, extraction, and high-volume passes;
Sonnet 4.6 for QA answers, playbook comparisons, and deviation summaries where
accuracy is load-bearing. The tier is selected by the caller via a `Tier` enum,
not by hardcoding model strings outside this module.

Implemented: Week 1 (client setup), Week 3 (QA routing), Week 5 (deviation routing).
"""
import enum
from typing import Any

import structlog
from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import Settings, get_settings

log = structlog.get_logger(__name__)


class Tier(enum.StrEnum):
    HAIKU = "haiku"    # classification, extraction, high-volume
    SONNET = "sonnet"  # QA answers, deviation summaries, load-bearing accuracy


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._models: dict[Tier, str] = {
            Tier.HAIKU: settings.anthropic_model_haiku,
            Tier.SONNET: settings.anthropic_model_sonnet,
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def complete(
        self,
        prompt: str,
        tier: Tier,
        *,
        system: str | None = None,
        max_tokens: int = 1024,
        trace_id: str | None = None,
    ) -> str:
        model = self._models[tier]
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        kwargs: dict[str, Any] = {"model": model, "max_tokens": max_tokens, "messages": messages}
        if system:
            kwargs["system"] = system

        log.debug("llm.complete", model=model, tier=tier.value, trace_id=trace_id)
        response = await self._client.messages.create(**kwargs)
        block = response.content[0]
        if block.type != "text":
            raise ValueError(f"Unexpected response content type: {block.type}")
        return block.text  # type: ignore[no-any-return]


_client: LLMClient | None = None


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient(settings or get_settings())
    return _client
