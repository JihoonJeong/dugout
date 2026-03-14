"""Daily prediction API 라우트."""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from daily.pipeline import DailyDataPipeline, DailyGame
from daily.predictor import DailyPredictor, GamePrediction
from daily.store import PredictionStore, UserPrediction
from data.pipeline import DugoutData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/daily", tags=["daily"])

# Module-level state (set during lifespan)
_pipeline: DailyDataPipeline | None = None
_predictor: DailyPredictor | None = None
_store: PredictionStore | None = None
_prediction_cache: dict[str, list[GamePrediction]] = {}  # date → predictions


def init_daily(data: DugoutData) -> None:
    """서버 시작 시 호출."""
    global _pipeline, _predictor, _store
    _pipeline = DailyDataPipeline()
    _predictor = DailyPredictor(data)
    _store = PredictionStore()
    logger.info("Daily prediction module initialized")


# ── Pydantic Models ──────────────────────────────────────

class GameCardResponse(BaseModel):
    game_id: int
    game_date: str
    game_time: str
    away_team_id: str
    home_team_id: str
    away_starter_name: str
    home_starter_name: str
    venue: str
    status: str

    # 엔진 예측
    mc_away_win_pct: float = 0.5
    mc_home_win_pct: float = 0.5
    final_away_win_pct: float = 0.5
    final_home_win_pct: float = 0.5
    mc_avg_away_runs: float = 0.0
    mc_avg_home_runs: float = 0.0
    mc_avg_total_runs: float = 0.0
    quick_away_score: int = 0
    quick_home_score: int = 0
    matchup_summary: str = ""
    away_starter_fallback: Optional[str] = None
    home_starter_fallback: Optional[str] = None

    # 사용자 예측 (있으면)
    user_prediction: Optional[dict] = None


class PredictionRequest(BaseModel):
    game_id: int
    game_date: str
    predicted_winner: str  # "away" | "home"
    predicted_away_score: Optional[int] = None
    predicted_home_score: Optional[int] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class PredictionUpdateRequest(BaseModel):
    game_date: str
    predicted_winner: Optional[str] = None
    predicted_away_score: Optional[int] = None
    predicted_home_score: Optional[int] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class ResultCardResponse(BaseModel):
    game_id: int
    game_date: str
    away_team_id: str
    home_team_id: str
    actual_away_score: int
    actual_home_score: int
    actual_winner: str

    # 엔진 예측
    engine_away_win_pct: float = 0.5
    engine_pick: str = ""

    # 사용자 예측
    user_prediction: Optional[dict] = None
    user_correct: Optional[bool] = None
    engine_correct: Optional[bool] = None

    # 채점
    score_breakdown: Optional[dict] = None


class MyStatsResponse(BaseModel):
    total_predictions: int = 0
    total_scored: int = 0
    wins_correct: int = 0
    wins_total: int = 0
    win_accuracy: float = 0.0
    exact_scores: int = 0
    total_points: float = 0.0
    avg_points: float = 0.0
    total_winner_points: int = 0
    total_score_points: float = 0.0
    total_calibration_points: float = 0.0
    engine_correct: int = 0
    engine_total: int = 0
    engine_accuracy: float = 0.0


# ── Endpoints ────────────────────────────────────────────

@router.get("/games/today")
def get_today_games() -> list[GameCardResponse]:
    """오늘 경기 목록 + 엔진 예측."""
    if _pipeline is None or _predictor is None or _store is None:
        raise HTTPException(500, "Daily module not initialized")

    today_str = date.today().isoformat()
    games = _pipeline.fetch_today()

    if not games:
        return []

    # 예측 캐시 확인
    if today_str not in _prediction_cache:
        predictions = _predictor.predict_all(games, n_sims=1000)
        _prediction_cache[today_str] = predictions
    else:
        predictions = _prediction_cache[today_str]

    pred_map = {p.game_id: p for p in predictions}
    user_preds = {p.game_id: p for p in _store.get_by_date(today_str)}

    result = []
    for game in games:
        pred = pred_map.get(game.game_id)
        up = user_preds.get(game.game_id)

        card = GameCardResponse(
            game_id=game.game_id,
            game_date=game.game_date,
            game_time=game.game_time,
            away_team_id=game.away_team_id,
            home_team_id=game.home_team_id,
            away_starter_name=game.away_starter_name,
            home_starter_name=game.home_starter_name,
            venue=game.venue,
            status=game.status,
            mc_away_win_pct=pred.mc_away_win_pct if pred else 0.5,
            mc_home_win_pct=pred.mc_home_win_pct if pred else 0.5,
            final_away_win_pct=pred.final_away_win_pct if pred else 0.5,
            final_home_win_pct=pred.final_home_win_pct if pred else 0.5,
            mc_avg_away_runs=pred.mc_avg_away_runs if pred else 0.0,
            mc_avg_home_runs=pred.mc_avg_home_runs if pred else 0.0,
            mc_avg_total_runs=pred.mc_avg_total_runs if pred else 0.0,
            quick_away_score=pred.quick_away_score if pred else 0,
            quick_home_score=pred.quick_home_score if pred else 0,
            matchup_summary=pred.matchup_summary if pred else "",
            away_starter_fallback=pred.away_starter_fallback if pred else None,
            home_starter_fallback=pred.home_starter_fallback if pred else None,
            user_prediction=asdict(up) if up else None,
        )
        result.append(card)

    return result


@router.get("/games/{target_date}")
def get_games_by_date(target_date: str) -> list[GameCardResponse]:
    """특정 날짜 경기 목록 + 엔진 예측."""
    if _pipeline is None or _predictor is None or _store is None:
        raise HTTPException(500, "Daily module not initialized")

    try:
        dt = date.fromisoformat(target_date)
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD")

    games = _pipeline.fetch_games(dt)
    if not games:
        return []

    if target_date not in _prediction_cache:
        predictions = _predictor.predict_all(games, n_sims=1000)
        _prediction_cache[target_date] = predictions
    else:
        predictions = _prediction_cache[target_date]

    pred_map = {p.game_id: p for p in predictions}
    user_preds = {p.game_id: p for p in _store.get_by_date(target_date)}

    result = []
    for game in games:
        pred = pred_map.get(game.game_id)
        up = user_preds.get(game.game_id)
        card = GameCardResponse(
            game_id=game.game_id,
            game_date=game.game_date,
            game_time=game.game_time,
            away_team_id=game.away_team_id,
            home_team_id=game.home_team_id,
            away_starter_name=game.away_starter_name,
            home_starter_name=game.home_starter_name,
            venue=game.venue,
            status=game.status,
            mc_away_win_pct=pred.mc_away_win_pct if pred else 0.5,
            mc_home_win_pct=pred.mc_home_win_pct if pred else 0.5,
            final_away_win_pct=pred.final_away_win_pct if pred else 0.5,
            final_home_win_pct=pred.final_home_win_pct if pred else 0.5,
            mc_avg_away_runs=pred.mc_avg_away_runs if pred else 0.0,
            mc_avg_home_runs=pred.mc_avg_home_runs if pred else 0.0,
            mc_avg_total_runs=pred.mc_avg_total_runs if pred else 0.0,
            quick_away_score=pred.quick_away_score if pred else 0,
            quick_home_score=pred.quick_home_score if pred else 0,
            matchup_summary=pred.matchup_summary if pred else "",
            away_starter_fallback=pred.away_starter_fallback if pred else None,
            home_starter_fallback=pred.home_starter_fallback if pred else None,
            user_prediction=asdict(up) if up else None,
        )
        result.append(card)

    return result


@router.post("/predictions")
def submit_prediction(req: PredictionRequest) -> dict:
    """예측 제출."""
    if _store is None or _pipeline is None:
        raise HTTPException(500, "Daily module not initialized")

    if req.predicted_winner not in ("away", "home"):
        raise HTTPException(400, "predicted_winner must be 'away' or 'home'")

    # 경기 존재 확인
    try:
        dt = date.fromisoformat(req.game_date)
    except ValueError:
        raise HTTPException(400, "Invalid date format")

    games = _pipeline.fetch_games(dt)
    game = next((g for g in games if g.game_id == req.game_id), None)
    if game is None:
        raise HTTPException(404, f"Game {req.game_id} not found on {req.game_date}")

    # 마감 체크 (경기 시작 1시간 전)
    if _is_locked(game):
        raise HTTPException(403, "Prediction window closed (game starts within 1 hour)")

    try:
        pred = _store.submit(
            game_id=req.game_id,
            game_date=req.game_date,
            away_team_id=game.away_team_id,
            home_team_id=game.home_team_id,
            predicted_winner=req.predicted_winner,
            predicted_away_score=req.predicted_away_score,
            predicted_home_score=req.predicted_home_score,
            confidence=req.confidence,
        )
        return {"status": "submitted", "prediction": asdict(pred)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/predictions/{prediction_id}")
def update_prediction(prediction_id: str, req: PredictionUpdateRequest) -> dict:
    """예측 수정."""
    if _store is None:
        raise HTTPException(500, "Daily module not initialized")

    try:
        pred = _store.update(
            prediction_id=prediction_id,
            game_date=req.game_date,
            predicted_winner=req.predicted_winner,
            predicted_away_score=req.predicted_away_score,
            predicted_home_score=req.predicted_home_score,
            confidence=req.confidence,
        )
        return {"status": "updated", "prediction": asdict(pred)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/results/yesterday")
def get_yesterday_results() -> list[ResultCardResponse]:
    """어제 결과 + 내 예측 비교."""
    if _pipeline is None or _store is None:
        raise HTTPException(500, "Daily module not initialized")

    yesterday = date.today() - timedelta(days=1)
    yesterday_str = yesterday.isoformat()

    results = _pipeline.fetch_yesterday_results()
    user_preds = {p.game_id: p for p in _store.get_by_date(yesterday_str)}

    # 캐시된 엔진 예측
    engine_preds = {}
    if yesterday_str in _prediction_cache:
        engine_preds = {p.game_id: p for p in _prediction_cache[yesterday_str]}

    # 실제 결과 기록 + 채점
    for r in results:
        ep = engine_preds.get(r.game_id)
        _store.record_results(
            game_id=r.game_id,
            game_date=r.game_date,
            actual_winner=r.winner,
            actual_away_score=r.away_score,
            actual_home_score=r.home_score,
            engine_win_pct=ep.final_away_win_pct if ep else None,
        )

    # reload after scoring
    user_preds = {p.game_id: p for p in _store.get_by_date(yesterday_str)}

    response = []
    for r in results:
        ep = engine_preds.get(r.game_id)
        up = user_preds.get(r.game_id)

        engine_pick = ""
        engine_away_pct = 0.5
        engine_correct = None
        if ep:
            engine_away_pct = ep.final_away_win_pct
            engine_pick = "away" if engine_away_pct > 0.5 else "home"
            engine_correct = (engine_pick == r.winner)

        score_bd = None
        if up and up.score_total is not None:
            score_bd = {
                "total": up.score_total,
                "winner": up.score_winner,
                "accuracy": up.score_accuracy,
                "exact_bonus": up.score_exact_bonus,
                "calibration": up.score_calibration,
            }

        response.append(ResultCardResponse(
            game_id=r.game_id,
            game_date=r.game_date,
            away_team_id=r.away_team_id,
            home_team_id=r.home_team_id,
            actual_away_score=r.away_score,
            actual_home_score=r.home_score,
            actual_winner=r.winner,
            engine_away_win_pct=engine_away_pct,
            engine_pick=engine_pick,
            user_prediction=asdict(up) if up else None,
            user_correct=up.correct if up else None,
            engine_correct=engine_correct,
            score_breakdown=score_bd,
        ))

    return response


@router.get("/my-stats")
def get_my_stats() -> MyStatsResponse:
    """내 누적 성적."""
    if _store is None:
        raise HTTPException(500, "Daily module not initialized")

    stats = _store.get_cumulative_stats()
    return MyStatsResponse(
        total_predictions=stats.total_predictions,
        total_scored=stats.total_scored,
        wins_correct=stats.wins_correct,
        wins_total=stats.wins_total,
        win_accuracy=stats.win_accuracy,
        exact_scores=stats.exact_scores,
        total_points=stats.total_points,
        avg_points=stats.avg_points,
        total_winner_points=stats.total_winner_points,
        total_score_points=stats.total_score_points,
        total_calibration_points=stats.total_calibration_points,
        engine_correct=stats.engine_correct,
        engine_total=stats.engine_total,
        engine_accuracy=stats.engine_accuracy,
    )


@router.get("/results/{target_date}")
def get_date_results(target_date: str) -> list[dict]:
    """특정 날짜 채점 상세."""
    if _store is None:
        raise HTTPException(500, "Daily module not initialized")

    try:
        date.fromisoformat(target_date)
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD")

    return _store.get_date_results(target_date)


def _is_locked(game: DailyGame) -> bool:
    """경기 시작 1시간 전이면 마감."""
    if not game.game_time or game.status != "Scheduled":
        return game.status != "Scheduled"  # 이미 시작된 경기는 마감

    try:
        game_dt = datetime.fromisoformat(f"{game.game_date}T{game.game_time}")
        now = datetime.now()
        return now >= game_dt - timedelta(hours=1)
    except (ValueError, TypeError):
        return False
