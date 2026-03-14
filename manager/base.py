"""Manager 추상 클래스 및 핵심 데이터 모델."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GameSituation:
    """매 타석 전 감독이 판단할 수 있는 상황 정보."""

    inning: int
    half: str  # "top" | "bottom"
    outs: int
    runners: dict[str, str]  # base → player_id
    score: dict[str, int]  # {"away": int, "home": int}

    batting_side: str  # "away" | "home"
    pitching_side: str

    # 현재 타자
    batter_id: str
    batter_name: str
    batter_hand: str
    batter_pa: int

    # 현재 투수
    pitcher_id: str
    pitcher_name: str
    pitcher_hand: str
    pitcher_pitch_count: int
    pitcher_innings: float
    pitcher_is_starter: bool

    # 팀 컨텍스트
    batting_order_idx: int
    bullpen_available: int  # 남은 불펜 수
    leverage_index: float


@dataclass
class ManagerDecision:
    """감독의 결정."""

    action: str  # "no_action", "pitching_change", "intentional_walk"
    reason: str = ""
    details: dict = field(default_factory=dict)
    # details for pitching_change: {"new_pitcher_id": str, "new_pitcher_name": str}
    # details for intentional_walk: {"walked_batter_id": str}


# 아무것도 하지 않음 — 기본 상태
NO_ACTION = ManagerDecision(action="no_action", reason="No intervention needed")


@dataclass
class DecisionEvent:
    """결정 기록."""

    inning: int
    half: str
    outs: int
    situation_summary: str
    decision: ManagerDecision
    leverage_index: float


class Manager(ABC):
    """감독 추상 클래스."""

    @abstractmethod
    def decide(self, situation: GameSituation) -> ManagerDecision:
        """현재 상황을 보고 결정을 내린다."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...
