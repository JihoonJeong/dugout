"""Claude (Anthropic) 어댑터."""

from __future__ import annotations

import json
import logging
from typing import Optional

from ..base import LLMAdvisor, LLMAnalysis, MatchupContext
from ..parser import parse_llm_response
from ..prompts import SYSTEM_PROMPT, build_analysis_prompt

logger = logging.getLogger(__name__)

MODELS = [
    "claude-sonnet-4-20250514",
    "claude-haiku-4-5-20251001",
]


class AnthropicAdvisor(LLMAdvisor):
    """Claude Messages API 어댑터."""

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def default_model(self) -> str:
        return MODELS[0]

    @property
    def available_models(self) -> list[str]:
        return MODELS

    async def analyze_matchup(
        self,
        context: MatchupContext,
        api_key: str,
        model: str | None = None,
    ) -> LLMAnalysis:
        model = model or self.default_model
        prompt = build_analysis_prompt(context)

        try:
            import httpx

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": 1024,
                        "system": SYSTEM_PROMPT,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            raw_text = data["content"][0]["text"]
            tokens = data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0)

            return parse_llm_response(raw_text, self.provider_name, model, tokens)

        except Exception as e:
            logger.error("Anthropic API error: %s", e)
            return LLMAnalysis(
                provider=self.provider_name,
                model=model,
                predicted_winner="home",
                confidence=0.5,
                error=str(e),
            )
