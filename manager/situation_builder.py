"""GameState → GameSituation 변환."""

from __future__ import annotations

from engine.models import GameState, Team
from .base import GameSituation
from .leverage import calculate_leverage


def build_situation(
    state: GameState,
    batting_team: Team,
    pitching_team: Team,
    batting_side: str,
    pitching_side: str,
) -> GameSituation:
    """엔진의 GameState를 감독용 GameSituation으로 변환."""

    batter_idx = state.batting_order_idx[batting_side]
    batter = batting_team.lineup[batter_idx]

    ps = state.current_pitcher[pitching_side]

    runners = {k: v.player_id for k, v in state.runners.items()}

    # 점수차 (pitching_side 기준)
    if pitching_side == "home":
        score_diff = state.score["home"] - state.score["away"]
    else:
        score_diff = state.score["away"] - state.score["home"]

    li = calculate_leverage(
        inning=state.inning,
        half=state.half,
        outs=state.outs,
        runners=runners,
        score_diff=score_diff,
    )

    # 남은 불펜 수
    bullpen_remaining = len(pitching_team.bullpen) - pitching_team._reliever_idx

    return GameSituation(
        inning=state.inning,
        half=state.half,
        outs=state.outs,
        runners=runners,
        score=dict(state.score),
        batting_side=batting_side,
        pitching_side=pitching_side,
        batter_id=batter.player_id,
        batter_name=batter.name,
        batter_hand=batter.hand,
        batter_pa=batter.pa,
        pitcher_id=ps.pitcher.player_id,
        pitcher_name=ps.pitcher.name,
        pitcher_hand=ps.pitcher.hand,
        pitcher_pitch_count=ps.pitch_count,
        pitcher_innings=ps.innings_pitched,
        pitcher_is_starter=ps.is_starter,
        batting_order_idx=batter_idx,
        bullpen_available=bullpen_remaining,
        leverage_index=li,
    )
