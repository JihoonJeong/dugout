"""LLM Advisor API 라우트 — 서버 프록시 (키 즉시 폐기)."""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from advisor.base import LLMAnalysis, MatchupContext
from advisor.adapters.anthropic import AnthropicAdvisor
from advisor.adapters.openai import OpenAIAdvisor
from advisor.adapters.google import GoogleAdvisor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/advisor", tags=["advisor"])

# 어댑터 레지스트리
_advisors = {
    "anthropic": AnthropicAdvisor(),
    "openai": OpenAIAdvisor(),
    "google": GoogleAdvisor(),
}


class AnalyzeRequest(BaseModel):
    provider: str  # "anthropic" | "openai" | "google"
    api_key: str
    model: Optional[str] = None

    # 매치업 데이터
    away_team_id: str
    home_team_id: str
    away_team_name: str = ""
    home_team_name: str = ""
    away_starter_name: str = ""
    home_starter_name: str = ""
    venue: str = ""
    game_time: str = ""

    # 엔진 예측
    engine_away_win_pct: float = 0.5
    engine_home_win_pct: float = 0.5
    engine_avg_away_runs: float = 0.0
    engine_avg_home_runs: float = 0.0
    engine_avg_total_runs: float = 0.0

    # 선발 스탯
    away_starter_k_rate: float = 0.0
    away_starter_bb_rate: float = 0.0
    away_starter_hr_rate: float = 0.0
    home_starter_k_rate: float = 0.0
    home_starter_bb_rate: float = 0.0
    home_starter_hr_rate: float = 0.0

    away_starter_fallback: Optional[str] = None
    home_starter_fallback: Optional[str] = None


class ProvidersResponse(BaseModel):
    providers: list[dict]


@router.get("/providers")
def get_providers() -> ProvidersResponse:
    """사용 가능한 LLM 프로바이더 목록."""
    providers = []
    for name, advisor in _advisors.items():
        providers.append({
            "name": name,
            "default_model": advisor.default_model,
            "models": advisor.available_models,
        })
    return ProvidersResponse(providers=providers)


@router.post("/analyze")
async def analyze_matchup(req: AnalyzeRequest) -> dict:
    """매치업 분석 요청. 키는 사용 후 즉시 폐기."""
    advisor = _advisors.get(req.provider)
    if advisor is None:
        raise HTTPException(400, f"Unknown provider: {req.provider}. Available: {list(_advisors.keys())}")

    if not req.api_key or len(req.api_key) < 10:
        raise HTTPException(400, "Invalid API key")

    context = MatchupContext(
        away_team_id=req.away_team_id,
        home_team_id=req.home_team_id,
        away_team_name=req.away_team_name or req.away_team_id,
        home_team_name=req.home_team_name or req.home_team_id,
        away_starter_name=req.away_starter_name,
        home_starter_name=req.home_starter_name,
        venue=req.venue,
        game_time=req.game_time,
        engine_away_win_pct=req.engine_away_win_pct,
        engine_home_win_pct=req.engine_home_win_pct,
        engine_avg_away_runs=req.engine_avg_away_runs,
        engine_avg_home_runs=req.engine_avg_home_runs,
        engine_avg_total_runs=req.engine_avg_total_runs,
        away_starter_k_rate=req.away_starter_k_rate,
        away_starter_bb_rate=req.away_starter_bb_rate,
        away_starter_hr_rate=req.away_starter_hr_rate,
        home_starter_k_rate=req.home_starter_k_rate,
        home_starter_bb_rate=req.home_starter_bb_rate,
        home_starter_hr_rate=req.home_starter_hr_rate,
        away_starter_fallback=req.away_starter_fallback,
        home_starter_fallback=req.home_starter_fallback,
    )

    # API 키는 이 스코프에서만 사용 — 함수 리턴 후 GC
    analysis = await advisor.analyze_matchup(context, req.api_key, req.model)

    return asdict(analysis)
