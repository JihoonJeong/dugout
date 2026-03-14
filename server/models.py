"""Pydantic Request/Response 모델."""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional


# ── Request Models ──

class NewGameRequest(BaseModel):
    away_team_id: str = Field(..., examples=["NYY"])
    home_team_id: str = Field(..., examples=["BOS"])
    mode: str = Field("spectate", description="spectate | advise | manage")
    away_philosophy: str = Field("analytics", description="감독 철학 프리셋")
    home_philosophy: str = Field("analytics", description="감독 철학 프리셋")
    seed: Optional[int] = None


class DecisionRequest(BaseModel):
    action: str = Field(..., description="pitching_change | intentional_walk | no_action")
    reason: str = Field("", description="유저 결정 사유")


# ── Response Models ──

class RunnerInfo(BaseModel):
    base: str
    player_id: str
    player_name: str


class PitcherInfo(BaseModel):
    player_id: str
    name: str
    hand: str
    pitch_count: int
    innings_pitched: float
    is_starter: bool


class BatterInfo(BaseModel):
    player_id: str
    name: str
    hand: str
    pa: int
    batting_order: int


class GameStateResponse(BaseModel):
    game_id: str
    inning: int
    half: str
    outs: int
    score: dict[str, int]
    runners: list[RunnerInfo]
    current_batter: BatterInfo
    current_pitcher: PitcherInfo
    is_game_over: bool
    winner: Optional[str] = None


class DecisionOption(BaseModel):
    action: str
    label: str
    reason: str


class AIRecommendation(BaseModel):
    action: str
    reason: str
    confidence: float


class AdvanceResponse(BaseModel):
    game_id: str

    # 타석 결과 (결정 포인트가 아닌 경우)
    play_result: Optional[str] = None
    play_description: Optional[str] = None

    # 결정 포인트
    decision_required: bool = False
    decision_options: list[DecisionOption] = []
    ai_recommendation: Optional[AIRecommendation] = None

    # 현재 상태
    state: GameStateResponse

    # 경기 종료
    is_game_over: bool = False


class PlayLogEntry(BaseModel):
    inning: int
    half: str
    batter: str
    pitcher: str
    event: str
    runs_scored: int
    description: str


class BoxScoreResponse(BaseModel):
    game_id: str
    score: dict[str, int]
    innings_played: int
    hits: dict[str, int]
    runs_by_inning: dict[str, list[int]]
    is_game_over: bool
    winner: Optional[str] = None


class NewGameResponse(BaseModel):
    game_id: str
    state: GameStateResponse
