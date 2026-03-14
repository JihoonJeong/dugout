"""Gemini (Google) 어댑터."""

from __future__ import annotations

import json
import logging
from typing import Optional

from ..base import LLMAdvisor, LLMAnalysis, MatchupContext
from ..parser import parse_llm_response
from ..prompts import SYSTEM_PROMPT, build_analysis_prompt

logger = logging.getLogger(__name__)

MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
]


class GoogleAdvisor(LLMAdvisor):
    """Google Gemini GenerateContent API 어댑터."""

    @property
    def provider_name(self) -> str:
        return "google"

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
        full_prompt = f"{SYSTEM_PROMPT}\n\n{prompt}"

        try:
            import httpx

            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    url,
                    params={"key": api_key},
                    headers={"Content-Type": "application/json"},
                    json={
                        "contents": [{"parts": [{"text": full_prompt}]}],
                        "generationConfig": {
                            "maxOutputTokens": 1024,
                            "responseMimeType": "application/json",
                        },
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            tokens = data.get("usageMetadata", {}).get("totalTokenCount", 0)

            return parse_llm_response(raw_text, self.provider_name, model, tokens)

        except Exception as e:
            logger.error("Google API error: %s", e)
            return LLMAnalysis(
                provider=self.provider_name,
                model=model,
                predicted_winner="home",
                confidence=0.5,
                error=str(e),
            )
