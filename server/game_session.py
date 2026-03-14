"""게임 세션 관리 — 메모리 내 상태 유지."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from data.constants import TEAM_MAPPING
from engine.at_bat import simulate_at_bat
from engine.constants import MANFRED_RUNNER_INNING
from engine.models import (
    GameState,
    LeagueStats,
    ParkFactors,
    PitcherState,
    PlayEvent,
    Runner,
    Team,
)
from engine.pitching import estimate_pitch_count
from engine.runners import resolve_play

from manager.base import DecisionEvent, Manager, ManagerDecision, NO_ACTION
from manager.situation_builder import build_situation
from manager.stat_manager import StatManager
from manager.philosophy import PRESETS, NEUTRAL
from manager.leverage import calculate_leverage

_HIT_EVENTS = {"1B", "2B", "3B", "HR"}


@dataclass
class PendingDecision:
    """사용자 결정을 기다리는 상태."""
    situation: object  # GameSituation
    options: list[dict]
    ai_recommendation: dict


@dataclass
class GameSession:
    """단일 경기 세션."""

    game_id: str
    mode: str  # spectate | advise | manage
    away_team: Team
    home_team: Team
    park: ParkFactors
    league: LeagueStats
    rng: np.random.Generator

    away_manager: StatManager
    home_manager: StatManager

    state: GameState
    runs_by_inning: dict[str, list[int]] = field(default_factory=lambda: {"away": [], "home": []})
    hits: dict[str, int] = field(default_factory=lambda: {"away": 0, "home": 0})
    total_pitches: dict[str, int] = field(default_factory=lambda: {"away": 0, "home": 0})
    decision_log: list[DecisionEvent] = field(default_factory=list)

    # 하프이닝 상태 추적
    half_runs: int = 0
    half_started: bool = False

    # 결정 대기
    pending_decision: Optional[PendingDecision] = None

    @property
    def is_game_over(self) -> bool:
        return self.state.game_over

    @property
    def winner(self) -> Optional[str]:
        if not self.state.game_over:
            return None
        if self.state.score["away"] > self.state.score["home"]:
            return "away"
        elif self.state.score["home"] > self.state.score["away"]:
            return "home"
        return "tie"

    @property
    def batting_side(self) -> str:
        return "away" if self.state.half == "top" else "home"

    @property
    def pitching_side(self) -> str:
        return "home" if self.state.half == "top" else "away"

    @property
    def batting_team(self) -> Team:
        return self.away_team if self.batting_side == "away" else self.home_team

    @property
    def pitching_team(self) -> Team:
        return self.away_team if self.pitching_side == "away" else self.home_team


class GameSessionManager:
    """게임 세션 저장소 (메모리 내)."""

    def __init__(self, teams: dict[str, Team], parks: dict, league: LeagueStats):
        self._sessions: dict[str, GameSession] = {}
        self._teams = teams
        self._parks = parks
        self._league = league

    def create_game(
        self,
        away_team_id: str,
        home_team_id: str,
        mode: str = "spectate",
        away_philosophy: str = "analytics",
        home_philosophy: str = "analytics",
        seed: int | None = None,
    ) -> GameSession:
        game_id = str(uuid.uuid4())[:8]

        away_team = self._teams[away_team_id]
        home_team = self._teams[home_team_id]

        park_name = TEAM_MAPPING[home_team_id]["park"]
        park = self._parks.get(park_name)
        if park is None:
            park = ParkFactors(park_name=park_name, pf_1b=100, pf_2b=100, pf_3b=100, pf_hr=100)

        rng = np.random.default_rng(seed)

        away_phil = PRESETS.get(away_philosophy, NEUTRAL)
        home_phil = PRESETS.get(home_philosophy, NEUTRAL)

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

        session = GameSession(
            game_id=game_id,
            mode=mode,
            away_team=away_team,
            home_team=home_team,
            park=park,
            league=self._league,
            rng=rng,
            away_manager=StatManager(away_phil),
            home_manager=StatManager(home_phil),
            state=state,
        )

        self._sessions[game_id] = session
        return session

    def get_session(self, game_id: str) -> GameSession | None:
        return self._sessions.get(game_id)

    def advance(self, session: GameSession, user_decision: ManagerDecision | None = None) -> dict:
        """한 타석 진행. 결정 포인트이면 중단하고 결정 요청을 반환."""
        st = session.state

        if st.game_over:
            return {"action": "game_over"}

        # 하프이닝 시작
        if not session.half_started:
            st.outs = 0
            st.runners = {}
            session.half_runs = 0
            if st.inning >= MANFRED_RUNNER_INNING:
                _place_manfred_runner(st, session.batting_team, session.batting_side)
            session.half_started = True

        batting_side = session.batting_side
        pitching_side = session.pitching_side

        # ── 결정 대기 중이었으면 처리 ──
        if session.pending_decision is not None and user_decision is not None:
            decision = user_decision
            session.pending_decision = None
        elif session.pending_decision is not None:
            # 유저가 결정을 안 보냄 — 다시 결정 요청
            return {"action": "decision_required", "pending": session.pending_decision}
        else:
            decision = None

        # ── 감독 결정 ──
        mgr = session.home_manager if pitching_side == "home" else session.away_manager
        situation = build_situation(
            st, session.batting_team, session.pitching_team,
            batting_side, pitching_side,
        )

        if decision is None:
            ai_decision = mgr.decide(situation)

            # 결정 포인트 판단
            is_decision_point = self._is_decision_point(situation, ai_decision)

            if is_decision_point and session.mode in ("advise", "manage"):
                options = self._build_options(situation, session)
                ai_rec = {
                    "action": ai_decision.action,
                    "reason": ai_decision.reason,
                    "confidence": 0.8 if ai_decision.action != "no_action" else 0.5,
                }
                session.pending_decision = PendingDecision(
                    situation=situation,
                    options=options,
                    ai_recommendation=ai_rec,
                )
                return {
                    "action": "decision_required",
                    "options": options,
                    "ai_recommendation": ai_rec,
                    "situation": situation,
                }
            else:
                decision = ai_decision

        # ── 결정 적용 ──
        if decision.action == "pitching_change":
            next_reliever = session.pitching_team.get_next_reliever()
            if next_reliever is not None:
                st.current_pitcher[pitching_side] = PitcherState(
                    pitcher=next_reliever,
                    pitch_count=0,
                    innings_pitched=0.0,
                    is_starter=False,
                )
                session.decision_log.append(DecisionEvent(
                    inning=st.inning, half=st.half, outs=st.outs,
                    situation_summary=f"Pitching change to {next_reliever.name}",
                    decision=decision, leverage_index=situation.leverage_index,
                ))

        elif decision.action == "intentional_walk":
            result = self._execute_ibb(session)
            if st.game_over:
                return {"action": "game_over", "play": result}
            return {"action": "ibb", "play": result}

        # ── 타석 시뮬레이션 ──
        ps = st.current_pitcher[pitching_side]
        batter_idx = st.batting_order_idx[batting_side]
        batter = session.batting_team.lineup[batter_idx]
        pitcher = ps.pitcher

        outs_before = st.outs
        runners_before = {k: v.player_id for k, v in st.runners.items()}

        ab_result = simulate_at_bat(batter, pitcher, session.league, session.park, session.rng)

        pitches = estimate_pitch_count(ab_result.event, session.rng)
        ps.pitch_count += pitches
        session.total_pitches[pitching_side] += pitches

        if ab_result.event in _HIT_EVENTS:
            session.hits[batting_side] += 1

        runners_after, runs, outs_added = resolve_play(
            ab_result.event, st.runners, st.outs,
            batter.player_id, batter.name, session.rng,
        )

        new_outs = st.outs + outs_added
        if new_outs >= 3:
            if new_outs > 3:
                runs = 0
            st.outs = 3
            st.runners = {}
        else:
            st.outs = new_outs
            st.runners = runners_after
            st.score[batting_side] += runs
            session.half_runs += runs

        ps.innings_pitched += outs_added / 3.0

        if st.outs >= 3 and outs_added <= 1:
            st.score[batting_side] += runs
            session.half_runs += runs

        runners_after_log = {k: v.player_id for k, v in st.runners.items()}
        play_event = PlayEvent(
            inning=st.inning, half=st.half,
            batter=batter.player_id, pitcher=pitcher.player_id,
            event=ab_result.event,
            runners_before=runners_before,
            runners_after=runners_after_log,
            runs_scored=runs,
            outs_before=outs_before, outs_after=st.outs,
            description=f"{batter.name} {ab_result.event}",
        )
        st.play_log.append(play_event)

        st.batting_order_idx[batting_side] = (batter_idx + 1) % 9

        # 워크오프 체크
        if _is_walkoff(st):
            st.game_over = True
            session.runs_by_inning[batting_side].append(session.half_runs)
            return {"action": "play", "play": play_event, "game_over": True}

        # 이닝 종료 체크
        if st.outs >= 3:
            session.runs_by_inning[batting_side].append(session.half_runs)
            session.half_started = False
            _advance_half_inning(st, session.runs_by_inning)

        return {"action": "play", "play": play_event, "game_over": st.game_over}

    def _is_decision_point(self, sit, ai_decision) -> bool:
        if ai_decision.action != "no_action":
            return True
        if sit.pitcher_pitch_count >= 85:
            return True
        if sit.leverage_index >= 2.0:
            return True
        if sit.outs == 0 and sit.pitcher_pitch_count > 0:
            # 이닝 시작 시 (첫 타석이 아닌 경우만)
            pass
        # IBB 적격
        has_scoring = "2B" in sit.runners or "3B" in sit.runners
        if has_scoring and "1B" not in sit.runners and sit.leverage_index >= 1.5:
            return True
        return False

    def _build_options(self, sit, session) -> list[dict]:
        options = [{"action": "no_action", "label": "Continue", "reason": "No change"}]
        if sit.bullpen_available > 0:
            options.append({
                "action": "pitching_change",
                "label": "Change pitcher",
                "reason": f"Current: {sit.pitcher_name} ({sit.pitcher_pitch_count}p, {sit.pitcher_innings:.1f}IP)",
            })
        has_scoring = "2B" in sit.runners or "3B" in sit.runners
        if has_scoring and "1B" not in sit.runners:
            options.append({
                "action": "intentional_walk",
                "label": f"IBB {sit.batter_name}",
                "reason": f"Walk {sit.batter_name} to set up force/DP",
            })
        return options

    def _execute_ibb(self, session) -> PlayEvent:
        st = session.state
        batting_side = session.batting_side
        pitching_side = session.pitching_side

        batter_idx = st.batting_order_idx[batting_side]
        batter = session.batting_team.lineup[batter_idx]

        outs_before = st.outs
        runners_before = {k: v.player_id for k, v in st.runners.items()}

        runners_after, runs, _ = resolve_play(
            "BB", st.runners, st.outs,
            batter.player_id, batter.name, session.rng,
        )
        st.runners = runners_after
        st.score[batting_side] += runs
        session.half_runs += runs

        runners_after_log = {k: v.player_id for k, v in st.runners.items()}
        play = PlayEvent(
            inning=st.inning, half=st.half,
            batter=batter.player_id,
            pitcher=st.current_pitcher[pitching_side].pitcher.player_id,
            event="IBB",
            runners_before=runners_before,
            runners_after=runners_after_log,
            runs_scored=runs,
            outs_before=outs_before,
            outs_after=st.outs,
            description=f"{batter.name} intentional walk",
        )
        st.play_log.append(play)
        st.batting_order_idx[batting_side] = (batter_idx + 1) % 9

        if _is_walkoff(st):
            st.game_over = True
            session.runs_by_inning[batting_side].append(session.half_runs)

        return play


# ── 헬퍼 (game.py에서 복사) ──

def _advance_half_inning(state: GameState, runs_by_inning) -> None:
    if state.half == "top":
        state.half = "bottom"
        if state.inning >= 9 and state.score["home"] > state.score["away"]:
            state.game_over = True
    else:
        if state.inning >= 9 and state.score["home"] != state.score["away"]:
            state.game_over = True
            return
        if state.inning >= 20:
            state.game_over = True
            return
        state.inning += 1
        state.half = "top"


def _is_walkoff(state: GameState) -> bool:
    return (state.half == "bottom" and state.inning >= 9
            and state.score["home"] > state.score["away"])


def _place_manfred_runner(state: GameState, batting_team: Team, batting_side: str) -> None:
    batter_idx = state.batting_order_idx[batting_side]
    runner_idx = (batter_idx - 1) % 9
    runner_player = batting_team.lineup[runner_idx]
    state.runners["2B"] = Runner(
        player_id=runner_player.player_id,
        name=runner_player.name,
        from_base="2B",
    )
