"""GPT (OpenAI) 어댑터."""

from __future__ import annotations

import json
import logging
from typing import Optional

from ..base import LLMAdvisor, LLMAnalysis, MatchupContext
from ..parser import parse_llm_response
from ..prompts import SYSTEM_PROMPT, build_analysis_prompt

logger = logging.getLogger(__name__)

MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4.1-mini",
]


class OpenAIAdvisor(LLMAdvisor):
    """OpenAI Chat Completions API 어댑터."""

    @property
    def provider_name(self) -> str:
        return "openai"

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
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": 1024,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        "response_format": {"type": "json_object"},
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            raw_text = data["choices"][0]["message"]["content"]
            tokens = data.get("usage", {}).get("total_tokens", 0)

            return parse_llm_response(raw_text, self.provider_name, model, tokens)

        except Exception as e:
            logger.error("OpenAI API error: %s", e)
            return LLMAnalysis(
                provider=self.provider_name,
                model=model,
                predicted_winner="home",
                confidence=0.5,
                error=str(e),
            )
