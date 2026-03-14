"""LLMAdvisor 인터페이스 + 데이터 모델."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MatchupContext:
    """LLM에 전달할 매치업 컨텍스트."""
    away_team_id: str
    home_team_id: str
    away_team_name: str
    home_team_name: str
    away_starter_name: str
    home_starter_name: str
    venue: str
    game_time: str

    # 엔진 예측
    engine_away_win_pct: float
    engine_home_win_pct: float
    engine_avg_away_runs: float
    engine_avg_home_runs: float
    engine_avg_total_runs: float

    # 선발 스탯
    away_starter_k_rate: float = 0.0
    away_starter_bb_rate: float = 0.0
    away_starter_hr_rate: float = 0.0
    home_starter_k_rate: float = 0.0
    home_starter_bb_rate: float = 0.0
    home_starter_hr_rate: float = 0.0

    # 팀 스탯 (옵션)
    away_team_avg: float = 0.0
    home_team_avg: float = 0.0

    # fallback 정보
    away_starter_fallback: Optional[str] = None
    home_starter_fallback: Optional[str] = None


@dataclass
class LLMAnalysis:
    """LLM 분석 결과."""
    provider: str  # "anthropic", "openai", "google"
    model: str     # "claude-sonnet-4-20250514", "gpt-4o", etc.

    # 핵심 분석
    predicted_winner: str  # "away" | "home"
    confidence: float      # 0.0 ~ 1.0
    predicted_away_score: Optional[int] = None
    predicted_home_score: Optional[int] = None

    # 분석 내용
    key_factors: list[str] = field(default_factory=list)  # 주요 요인 3~5개
    analysis: str = ""      # 자연어 분석 (2~3문장)
    risk_factors: list[str] = field(default_factory=list)  # 리스크 요인

    # 메타
    tokens_used: int = 0
    error: Optional[str] = None


class LLMAdvisor(ABC):
    """LLM 어드바이저 인터페이스."""

    @abstractmethod
    async def analyze_matchup(
        self,
        context: MatchupContext,
        api_key: str,
        model: str | None = None,
    ) -> LLMAnalysis:
        """매치업 분석 요청."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @property
    @abstractmethod
    def default_model(self) -> str:
        ...

    @property
    @abstractmethod
    def available_models(self) -> list[str]:
        ...
