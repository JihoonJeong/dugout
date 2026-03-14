"""경기 시뮬레이션 엔진 — Phase 0-CD 핵심."""

import numpy as np

from .at_bat import simulate_at_bat
from .constants import MANFRED_RUNNER_INNING, MAX_INNINGS
from .models import (
    GameResult,
    GameState,
    LeagueStats,
    ParkFactors,
    PitcherState,
    PlayEvent,
    Runner,
    Team,
)
from .pitching import check_pitching_change, estimate_pitch_count
from .runners import resolve_play


_HIT_EVENTS = {"1B", "2B", "3B", "HR"}


def simulate_game(
    away_team: Team,
    home_team: Team,
    park: ParkFactors,
    league: LeagueStats,
    rng: np.random.Generator,
) -> GameResult:
    """한 경기를 처음부터 끝까지 시뮬레이션."""

    state = GameState(
        inning=1,
        half="top",
        outs=0,
        runners={},
        score={"away": 0, "home": 0},
        batting_order_idx={"away": 0, "home": 0},
        current_pitcher={
            "away": PitcherState(away_team.starter, pitch_count=0, innings_pitched=0.0, is_starter=True),
            "home": PitcherState(home_team.starter, pitch_count=0, innings_pitched=0.0, is_starter=True),
        },
        game_over=False,
        play_log=[],
    )

    # 이닝별 득점 추적
    runs_by_inning: dict[str, list[int]] = {"away": [], "home": []}
    hits: dict[str, int] = {"away": 0, "home": 0}
    total_pitches: dict[str, int] = {"away": 0, "home": 0}

    while not state.game_over:
        batting_side = "away" if state.half == "top" else "home"
        pitching_side = "home" if state.half == "top" else "away"

        batting_team = away_team if batting_side == "away" else home_team
        pitching_team = away_team if pitching_side == "away" else home_team

        # 하프이닝 시작: 초기화
        state.outs = 0
        state.runners = {}

        # Manfred Runner
        if state.inning >= MANFRED_RUNNER_INNING:
            _place_manfred_runner(state, batting_team, batting_side)

        half_runs = 0

        while state.outs < 3:
            # 투수 교체 판정
            ps = state.current_pitcher[pitching_side]
            ps = check_pitching_change(ps, pitching_team)
            state.current_pitcher[pitching_side] = ps

            # 현재 타자
            batter_idx = state.batting_order_idx[batting_side]
            batter = batting_team.lineup[batter_idx]
            pitcher = ps.pitcher

            # 플레이 전 상태 기록
            outs_before = state.outs
            runners_before = {k: v.player_id for k, v in state.runners.items()}

            # 타석 시뮬레이션
            ab_result = simulate_at_bat(batter, pitcher, league, park, rng)

            # 투구 수
            pitches = estimate_pitch_count(ab_result.event, rng)
            ps.pitch_count += pitches
            total_pitches[pitching_side] += pitches

            # 안타 카운트
            if ab_result.event in _HIT_EVENTS:
                hits[batting_side] += 1

            # 주자 진루 해결
            runners_after, runs, outs_added = resolve_play(
                ab_result.event,
                state.runners,
                state.outs,
                batter.player_id,
                batter.name,
                rng,
            )

            # 3아웃 초과 방지
            new_outs = state.outs + outs_added
            if new_outs >= 3:
                # 3아웃 동시 달성 시 그 플레이의 득점은 인정하지 않음 (타임 플레이)
                # 단, 아웃보다 먼저 홈을 밟은 주자는 득점 인정
                # V0.1 단순화: 3아웃 달성 시 해당 플레이 득점 무효
                if new_outs > 3:
                    runs = 0
                state.outs = 3
                state.runners = {}
            else:
                state.outs = new_outs
                state.runners = runners_after
                state.score[batting_side] += runs
                half_runs += runs

            # 투구 이닝 업데이트
            ps.innings_pitched += outs_added / 3.0

            # outs가 3이 된 경우에도 아웃 전 득점은 이미 처리됨
            # (3아웃과 동시에 발생하는 경우만 위에서 제외)
            if state.outs >= 3 and outs_added <= 1:
                # 단일 아웃으로 이닝 종료: 이 플레이 득점은 유효
                state.score[batting_side] += runs
                half_runs += runs

            # 플레이 기록
            runners_after_log = {k: v.player_id for k, v in state.runners.items()}
            state.play_log.append(PlayEvent(
                inning=state.inning,
                half=state.half,
                batter=batter.player_id,
                pitcher=pitcher.player_id,
                event=ab_result.event,
                runners_before=runners_before,
                runners_after=runners_after_log,
                runs_scored=runs,
                outs_before=outs_before,
                outs_after=state.outs,
                description=f"{batter.name} {ab_result.event}",
            ))

            # 타순 진행
            state.batting_order_idx[batting_side] = (batter_idx + 1) % 9

            # 워크오프 체크
            if _is_walkoff(state):
                state.game_over = True
                break

        # 이닝 득점 기록
        runs_by_inning[batting_side].append(half_runs)

        if not state.game_over:
            _advance_half_inning(state, runs_by_inning)

    # 결과 생성
    winner = "tie"
    if state.score["away"] > state.score["home"]:
        winner = "away"
    elif state.score["home"] > state.score["away"]:
        winner = "home"

    return GameResult(
        score=dict(state.score),
        winner=winner,
        innings_played=state.inning,
        play_log=state.play_log,
        hits=hits,
        runs_by_inning=runs_by_inning,
        total_pitches=total_pitches,
    )


def _advance_half_inning(
    state: GameState,
    runs_by_inning: dict[str, list[int]],
) -> None:
    """하프이닝 전환."""
    if state.half == "top":
        state.half = "bottom"

        # 9회말: 홈팀이 이미 리드 중이면 경기 종료
        if state.inning >= 9 and state.score["home"] > state.score["away"]:
            state.game_over = True
            return
    else:
        # bottom 끝
        if state.inning >= 9 and state.score["home"] != state.score["away"]:
            state.game_over = True
            return

        # 최대 이닝 초과 시 무승부
        if state.inning >= MAX_INNINGS:
            state.game_over = True
            return

        state.inning += 1
        state.half = "top"


def _is_walkoff(state: GameState) -> bool:
    """9회말 이후, 홈팀이 리드하면 즉시 종료."""
    if state.half != "bottom":
        return False
    if state.inning < 9:
        return False
    return state.score["home"] > state.score["away"]


def _place_manfred_runner(
    state: GameState,
    batting_team: Team,
    batting_side: str,
) -> None:
    """10회+ 하프이닝 시작 시 2루에 자동 주자 배치."""
    batter_idx = state.batting_order_idx[batting_side]
    runner_idx = (batter_idx - 1) % 9
    runner_player = batting_team.lineup[runner_idx]

    state.runners["2B"] = Runner(
        player_id=runner_player.player_id,
        name=runner_player.name,
        from_base="2B",
    )
