"""LLM 응답 파싱."""

from __future__ import annotations

import json
import re
from typing import Optional

from .base import LLMAnalysis


def parse_llm_response(
    raw_text: str,
    provider: str,
    model: str,
    tokens_used: int = 0,
) -> LLMAnalysis:
    """LLM 텍스트 응답 → LLMAnalysis 변환.

    JSON 블록을 추출하고 파싱. 마크다운 코드 블록 처리.
    """
    try:
        data = _extract_json(raw_text)
    except (json.JSONDecodeError, ValueError) as e:
        return LLMAnalysis(
            provider=provider,
            model=model,
            predicted_winner="home",
            confidence=0.5,
            error=f"Failed to parse response: {e}",
            tokens_used=tokens_used,
        )

    winner = data.get("predicted_winner", "home")
    if winner not in ("away", "home"):
        winner = "home"

    confidence = data.get("confidence", 0.5)
    confidence = max(0.0, min(1.0, float(confidence)))

    away_score = data.get("predicted_away_score")
    home_score = data.get("predicted_home_score")
    if away_score is not None:
        away_score = max(0, int(away_score))
    if home_score is not None:
        home_score = max(0, int(home_score))

    key_factors = data.get("key_factors", [])
    if not isinstance(key_factors, list):
        key_factors = [str(key_factors)]

    risk_factors = data.get("risk_factors", [])
    if not isinstance(risk_factors, list):
        risk_factors = [str(risk_factors)]

    analysis = data.get("analysis", "")

    return LLMAnalysis(
        provider=provider,
        model=model,
        predicted_winner=winner,
        confidence=confidence,
        predicted_away_score=away_score,
        predicted_home_score=home_score,
        key_factors=key_factors[:5],
        analysis=str(analysis),
        risk_factors=risk_factors[:3],
        tokens_used=tokens_used,
    )


def _extract_json(text: str) -> dict:
    """텍스트에서 JSON 추출. 코드 블록, raw JSON 모두 지원."""
    # 1. ```json ... ``` 블록
    match = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())

    # 2. { ... } 직접 탐색
    start = text.find('{')
    if start == -1:
        raise ValueError("No JSON object found in response")

    # 중첩 브레이스 추적
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])

    raise ValueError("Unclosed JSON object")
