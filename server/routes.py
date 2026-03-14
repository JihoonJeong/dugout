"""FastAPI 라우트."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from manager.base import ManagerDecision
from .game_session import GameSession, GameSessionManager
from .models import (
    AdvanceResponse,
    AIRecommendation,
    BatterInfo,
    BoxScoreResponse,
    DecisionOption,
    DecisionRequest,
    GameStateResponse,
    NewGameRequest,
    NewGameResponse,
    PlayLogEntry,
    PitcherInfo,
    RunnerInfo,
)

router = APIRouter()

# session_manager는 app.py에서 주입
_session_mgr: GameSessionManager | None = None


def set_session_manager(mgr: GameSessionManager) -> None:
    global _session_mgr
    _session_mgr = mgr


def _mgr() -> GameSessionManager:
    if _session_mgr is None:
        raise HTTPException(500, "Session manager not initialized")
    return _session_mgr


def _build_state_response(s: GameSession) -> GameStateResponse:
    st = s.state
    batter_idx = st.batting_order_idx[s.batting_side]
    batter = s.batting_team.lineup[batter_idx]
    ps = st.current_pitcher[s.pitching_side]

    runners = []
    for base, runner in st.runners.items():
        runners.append(RunnerInfo(base=base, player_id=runner.player_id, player_name=runner.name))

    return GameStateResponse(
        game_id=s.game_id,
        inning=st.inning,
        half=st.half,
        outs=st.outs,
        score=dict(st.score),
        runners=runners,
        current_batter=BatterInfo(
            player_id=batter.player_id,
            name=batter.name,
            hand=batter.hand,
            pa=batter.pa,
            batting_order=batter_idx + 1,
        ),
        current_pitcher=PitcherInfo(
            player_id=ps.pitcher.player_id,
            name=ps.pitcher.name,
            hand=ps.pitcher.hand,
            pitch_count=ps.pitch_count,
            innings_pitched=ps.innings_pitched,
            is_starter=ps.is_starter,
        ),
        is_game_over=s.is_game_over,
        winner=s.winner,
    )


@router.post("/game/new", response_model=NewGameResponse)
def create_game(req: NewGameRequest):
    mgr = _mgr()
    try:
        session = mgr.create_game(
            away_team_id=req.away_team_id,
            home_team_id=req.home_team_id,
            mode=req.mode,
            away_philosophy=req.away_philosophy,
            home_philosophy=req.home_philosophy,
            seed=req.seed,
        )
    except KeyError as e:
        raise HTTPException(400, f"Unknown team: {e}")

    return NewGameResponse(
        game_id=session.game_id,
        state=_build_state_response(session),
    )


@router.get("/game/{game_id}/state", response_model=GameStateResponse)
def get_state(game_id: str):
    session = _mgr().get_session(game_id)
    if session is None:
        raise HTTPException(404, "Game not found")
    return _build_state_response(session)


@router.post("/game/{game_id}/advance", response_model=AdvanceResponse)
def advance_game(game_id: str):
    session = _mgr().get_session(game_id)
    if session is None:
        raise HTTPException(404, "Game not found")

    result = _mgr().advance(session)

    state = _build_state_response(session)

    if result["action"] == "decision_required":
        pending = result.get("pending") or result
        options_raw = pending.get("options", result.get("options", []))
        ai_rec_raw = pending.get("ai_recommendation", result.get("ai_recommendation"))

        options = [DecisionOption(**o) for o in options_raw] if options_raw else []
        ai_rec = AIRecommendation(**ai_rec_raw) if ai_rec_raw else None

        return AdvanceResponse(
            game_id=game_id,
            decision_required=True,
            decision_options=options,
            ai_recommendation=ai_rec,
            state=state,
        )

    play = result.get("play")
    play_result = None
    play_desc = None
    if play is not None:
        play_result = play.event if hasattr(play, "event") else str(play)
        play_desc = play.description if hasattr(play, "description") else None

    return AdvanceResponse(
        game_id=game_id,
        play_result=play_result,
        play_description=play_desc,
        state=state,
        is_game_over=session.is_game_over,
    )


@router.post("/game/{game_id}/decide", response_model=AdvanceResponse)
def decide(game_id: str, req: DecisionRequest):
    session = _mgr().get_session(game_id)
    if session is None:
        raise HTTPException(404, "Game not found")

    decision = ManagerDecision(action=req.action, reason=req.reason)
    result = _mgr().advance(session, user_decision=decision)

    state = _build_state_response(session)
    play = result.get("play")

    return AdvanceResponse(
        game_id=game_id,
        play_result=play.event if play and hasattr(play, "event") else None,
        play_description=play.description if play and hasattr(play, "description") else None,
        state=state,
        is_game_over=session.is_game_over,
    )


@router.get("/game/{game_id}/boxscore", response_model=BoxScoreResponse)
def get_boxscore(game_id: str):
    session = _mgr().get_session(game_id)
    if session is None:
        raise HTTPException(404, "Game not found")

    return BoxScoreResponse(
        game_id=game_id,
        score=dict(session.state.score),
        innings_played=session.state.inning,
        hits=session.hits,
        runs_by_inning=session.runs_by_inning,
        is_game_over=session.is_game_over,
        winner=session.winner,
    )


@router.get("/game/{game_id}/log", response_model=list[PlayLogEntry])
def get_log(game_id: str):
    session = _mgr().get_session(game_id)
    if session is None:
        raise HTTPException(404, "Game not found")

    return [
        PlayLogEntry(
            inning=p.inning,
            half=p.half,
            batter=p.batter,
            pitcher=p.pitcher,
            event=p.event,
            runs_scored=p.runs_scored,
            description=p.description,
        )
        for p in session.state.play_log
    ]
