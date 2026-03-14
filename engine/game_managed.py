"""감독 개입이 있는 경기 시뮬레이션 — game.py 래퍼.

기존 Phase 0 엔진 코드(game.py, at_bat.py 등)를 수정하지 않음.
매 타석 전에 Manager.decide()를 호출하여 투수 교체 / 고의사구를 처리.
"""

from __future__ import annotations

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
from .pitching import estimate_pitch_count
from .runners import resolve_play

from manager.base import DecisionEvent, Manager, ManagerDecision, NO_ACTION
from manager.situation_builder import build_situation

_HIT_EVENTS = {"1B", "2B", "3B", "HR"}


def simulate_managed_game(
    away_team: Team,
    home_team: Team,
    park: ParkFactors,
    league: LeagueStats,
    rng: np.random.Generator,
    away_manager: Manager | None = None,
    home_manager: Manager | None = None,
) -> tuple[GameResult, list[DecisionEvent]]:
    """감독 개입이 있는 경기 시뮬레이션.

    Returns:
        (GameResult, decision_log)
    """
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

    runs_by_inning: dict[str, list[int]] = {"away": [], "home": []}
    hits: dict[str, int] = {"away": 0, "home": 0}
    total_pitches: dict[str, int] = {"away": 0, "home": 0}
    decision_log: list[DecisionEvent] = []

    managers = {"away": away_manager, "home": home_manager}

    while not state.game_over:
        batting_side = "away" if state.half == "top" else "home"
        pitching_side = "home" if state.half == "top" else "away"

        batting_team = away_team if batting_side == "away" else home_team
        pitching_team = away_team if pitching_side == "away" else home_team

        state.outs = 0
        state.runners = {}

        if state.inning >= MANFRED_RUNNER_INNING:
            _place_manfred_runner(state, batting_team, batting_side)

        half_runs = 0

        while state.outs < 3:
            # ── 감독 결정 (투수 교체) ──
            mgr = managers[pitching_side]
            if mgr is not None:
                situation = build_situation(
                    state, batting_team, pitching_team, batting_side, pitching_side,
                )
                decision = mgr.decide(situation)
                if decision.action != "no_action":
                    decision_log.extend(
                        getattr(mgr, "decision_log", [])[-1:]
                        if hasattr(mgr, "decision_log") else []
                    )

                if decision.action == "pitching_change":
                    ps = state.current_pitcher[pitching_side]
                    next_reliever = pitching_team.get_next_reliever()
                    if next_reliever is not None:
                        state.current_pitcher[pitching_side] = PitcherState(
                            pitcher=next_reliever,
                            pitch_count=0,
                            innings_pitched=0.0,
                            is_starter=False,
                        )

                elif decision.action == "intentional_walk":
                    # 고의사구 처리: BB와 동일한 포스 진루
                    batter_idx = state.batting_order_idx[batting_side]
                    batter = batting_team.lineup[batter_idx]

                    outs_before = state.outs
                    runners_before = {k: v.player_id for k, v in state.runners.items()}

                    runners_after, runs, outs_added = resolve_play(
                        "BB", state.runners, state.outs,
                        batter.player_id, batter.name, rng,
                    )
                    state.runners = runners_after
                    state.score[batting_side] += runs
                    half_runs += runs

                    # 투구 수는 추가하지 않음 (2023+ 규칙)

                    runners_after_log = {k: v.player_id for k, v in state.runners.items()}
                    state.play_log.append(PlayEvent(
                        inning=state.inning,
                        half=state.half,
                        batter=batter.player_id,
                        pitcher=state.current_pitcher[pitching_side].pitcher.player_id,
                        event="IBB",
                        runners_before=runners_before,
                        runners_after=runners_after_log,
                        runs_scored=runs,
                        outs_before=outs_before,
                        outs_after=state.outs,
                        description=f"{batter.name} intentional walk",
                    ))

                    state.batting_order_idx[batting_side] = (batter_idx + 1) % 9

                    if _is_walkoff(state):
                        state.game_over = True
                        break
                    continue  # 다음 타자로

            else:
                # 감독 없음 — Phase 0 자동 규칙으로 투수 교체
                from .pitching import check_pitching_change
                ps = state.current_pitcher[pitching_side]
                ps = check_pitching_change(ps, pitching_team)
                state.current_pitcher[pitching_side] = ps

            # ── 타석 시뮬레이션 (Phase 0 동일) ──
            ps = state.current_pitcher[pitching_side]
            batter_idx = state.batting_order_idx[batting_side]
            batter = batting_team.lineup[batter_idx]
            pitcher = ps.pitcher

            outs_before = state.outs
            runners_before = {k: v.player_id for k, v in state.runners.items()}

            ab_result = simulate_at_bat(batter, pitcher, league, park, rng)

            pitches = estimate_pitch_count(ab_result.event, rng)
            ps.pitch_count += pitches
            total_pitches[pitching_side] += pitches

            if ab_result.event in _HIT_EVENTS:
                hits[batting_side] += 1

            runners_after, runs, outs_added = resolve_play(
                ab_result.event, state.runners, state.outs,
                batter.player_id, batter.name, rng,
            )

            new_outs = state.outs + outs_added
            if new_outs >= 3:
                if new_outs > 3:
                    runs = 0
                state.outs = 3
                state.runners = {}
            else:
                state.outs = new_outs
                state.runners = runners_after
                state.score[batting_side] += runs
                half_runs += runs

            ps.innings_pitched += outs_added / 3.0

            if state.outs >= 3 and outs_added <= 1:
                state.score[batting_side] += runs
                half_runs += runs

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

            state.batting_order_idx[batting_side] = (batter_idx + 1) % 9

            if _is_walkoff(state):
                state.game_over = True
                break

        runs_by_inning[batting_side].append(half_runs)

        if not state.game_over:
            _advance_half_inning(state, runs_by_inning)

    winner = "tie"
    if state.score["away"] > state.score["home"]:
        winner = "away"
    elif state.score["home"] > state.score["away"]:
        winner = "home"

    result = GameResult(
        score=dict(state.score),
        winner=winner,
        innings_played=state.inning,
        play_log=state.play_log,
        hits=hits,
        runs_by_inning=runs_by_inning,
        total_pitches=total_pitches,
    )

    return result, decision_log


# ── game.py에서 복사한 헬퍼 (엔진 수정 없이 재사용) ──

def _advance_half_inning(state: GameState, runs_by_inning: dict[str, list[int]]) -> None:
    if state.half == "top":
        state.half = "bottom"
        if state.inning >= 9 and state.score["home"] > state.score["away"]:
            state.game_over = True
            return
    else:
        if state.inning >= 9 and state.score["home"] != state.score["away"]:
            state.game_over = True
            return
        if state.inning >= MAX_INNINGS:
            state.game_over = True
            return
        state.inning += 1
        state.half = "top"


def _is_walkoff(state: GameState) -> bool:
    if state.half != "bottom":
        return False
    if state.inning < 9:
        return False
    return state.score["home"] > state.score["away"]


def _place_manfred_runner(state: GameState, batting_team: Team, batting_side: str) -> None:
    batter_idx = state.batting_order_idx[batting_side]
    runner_idx = (batter_idx - 1) % 9
    runner_player = batting_team.lineup[runner_idx]
    state.runners["2B"] = Runner(
        player_id=runner_player.player_id,
        name=runner_player.name,
        from_base="2B",
    )
