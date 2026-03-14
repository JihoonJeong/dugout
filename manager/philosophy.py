"""감독 철학 — 결정 스타일 파라미터."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ManagerPhilosophy:
    """감독의 경기 운영 철학."""

    name: str

    # 투수 교체 기준
    starter_pitch_limit: int  # 선발 교체 투구수 기준
    starter_inning_limit: float  # 선발 최대 이닝
    reliever_inning_limit: float  # 불펜 최대 이닝

    # 고의사구 성향
    ibb_aggression: float  # 0.0=안함, 1.0=적극적
    ibb_leverage_threshold: float  # 이 이상 LI에서만 IBB 고려

    # 투수 교체 민감도
    pitch_count_sensitivity: float  # 높을수록 투구수에 민감하게 교체
    leverage_sensitivity: float  # 높을수록 LI에 따라 빨리 교체


# ── 5개 프리셋 ──

MONEYBALL = ManagerPhilosophy(
    name="moneyball",
    starter_pitch_limit=105,
    starter_inning_limit=7.0,
    reliever_inning_limit=1.0,
    ibb_aggression=0.3,
    ibb_leverage_threshold=2.5,
    pitch_count_sensitivity=0.8,
    leverage_sensitivity=0.7,
)

OLD_SCHOOL = ManagerPhilosophy(
    name="old_school",
    starter_pitch_limit=115,
    starter_inning_limit=8.0,
    reliever_inning_limit=2.0,
    ibb_aggression=0.8,
    ibb_leverage_threshold=1.5,
    pitch_count_sensitivity=0.3,
    leverage_sensitivity=0.4,
)

ANALYTICS = ManagerPhilosophy(
    name="analytics",
    starter_pitch_limit=95,
    starter_inning_limit=6.0,
    reliever_inning_limit=1.0,
    ibb_aggression=0.5,
    ibb_leverage_threshold=2.0,
    pitch_count_sensitivity=1.0,
    leverage_sensitivity=1.0,
)

WIN_NOW = ManagerPhilosophy(
    name="win_now",
    starter_pitch_limit=100,
    starter_inning_limit=6.0,
    reliever_inning_limit=1.0,
    ibb_aggression=0.6,
    ibb_leverage_threshold=1.8,
    pitch_count_sensitivity=0.9,
    leverage_sensitivity=0.9,
)

DEVELOPMENT = ManagerPhilosophy(
    name="development",
    starter_pitch_limit=110,
    starter_inning_limit=7.0,
    reliever_inning_limit=2.0,
    ibb_aggression=0.2,
    ibb_leverage_threshold=3.0,
    pitch_count_sensitivity=0.4,
    leverage_sensitivity=0.3,
)

PRESETS: dict[str, ManagerPhilosophy] = {
    "moneyball": MONEYBALL,
    "old_school": OLD_SCHOOL,
    "analytics": ANALYTICS,
    "win_now": WIN_NOW,
    "development": DEVELOPMENT,
}

# 중립 — Phase 0 자동 규칙과 유사하게 설정
NEUTRAL = ManagerPhilosophy(
    name="neutral",
    starter_pitch_limit=100,
    starter_inning_limit=6.0,
    reliever_inning_limit=1.0,
    ibb_aggression=0.0,
    ibb_leverage_threshold=99.0,  # IBB 안 함
    pitch_count_sensitivity=0.5,
    leverage_sensitivity=0.5,
)
