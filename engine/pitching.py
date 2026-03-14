"""투수 교체 로직 (V0.1 자동 규칙)."""

import numpy as np

from data.runner_tables import MEAN_PITCHES_PER_EVENT
from .constants import (
    PITCH_COUNT_MAX,
    PITCH_COUNT_STD,
    RELIEVER_INNING_LIMIT,
    STARTER_INNING_LIMIT,
    STARTER_PITCH_LIMIT,
)
from .models import PitcherState, Team


def check_pitching_change(
    current_ps: PitcherState,
    pitching_team: Team,
) -> PitcherState:
    """투수 교체 판정. 교체 시 새 PitcherState 반환, 아니면 현재 반환."""
    if current_ps.is_starter:
        should_change = (
            current_ps.pitch_count >= STARTER_PITCH_LIMIT
            or current_ps.innings_pitched >= STARTER_INNING_LIMIT
        )
        if should_change:
            next_reliever = pitching_team.get_next_reliever()
            if next_reliever is not None:
                return PitcherState(
                    pitcher=next_reliever,
                    pitch_count=0,
                    innings_pitched=0.0,
                    is_starter=False,
                )
    else:
        if current_ps.innings_pitched >= RELIEVER_INNING_LIMIT:
            next_reliever = pitching_team.get_next_reliever()
            if next_reliever is not None:
                return PitcherState(
                    pitcher=next_reliever,
                    pitch_count=0,
                    innings_pitched=0.0,
                    is_starter=False,
                )

    return current_ps


def estimate_pitch_count(event: str, rng: np.random.Generator) -> int:
    """타석 결과에 따른 투구 수 근사."""
    mean = MEAN_PITCHES_PER_EVENT[event]
    count = max(1, round(rng.normal(mean, PITCH_COUNT_STD)))
    return min(count, PITCH_COUNT_MAX)
