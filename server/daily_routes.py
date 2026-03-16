"""Daily prediction API 라우트."""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from daily.manager import Manager, ManagerStore
from daily.pipeline import DailyDataPipeline, DailyGame
from daily.pipelines.kbo import KBOPipeline
from daily.pipelines.npb import NPBPipeline
from daily.predictor import DailyPredictor, GamePrediction, MultiLeaguePredictor
from daily.store import PredictionStore, UserPrediction
from data.pipeline import DugoutData
from data.leagues.kbo.pipeline import build_kbo_data
from data.leagues.npb.pipeline import build_npb_data

logger = logging.getLogger(__name__)

# League timezone mapping for per-league "today" calculation
LEAGUE_TZS = {
    "mlb": ZoneInfo("America/New_York"),
    "kbo": ZoneInfo("Asia/Seoul"),
    "npb": ZoneInfo("Asia/Tokyo"),
}

router = APIRouter(prefix="/daily", tags=["daily"])

# Module-level state (set during lifespan)
_pipeline: DailyDataPipeline | None = None
_kbo_pipeline: KBOPipeline | None = None
_npb_pipeline: NPBPipeline | None = None
_predictor: DailyPredictor | None = None
_store: PredictionStore | None = None
_manager_store: ManagerStore | None = None
_prediction_cache: dict[str, list[GamePrediction]] = {}  # date → predictions


def init_daily(data: DugoutData) -> None:
    """서버 시작 시 호출."""
    global _pipeline, _kbo_pipeline, _npb_pipeline, _predictor, _store, _manager_store
    _pipeline = DailyDataPipeline()
    _kbo_pipeline = KBOPipeline()
    _npb_pipeline = NPBPipeline()

    # KBO/NPB 데이터 로드 (실패해도 MLB는 동작)
    kbo_data = None
    npb_data = None
    try:
        kbo_data = build_kbo_data()
        logger.info("KBO data loaded: %d teams", len(kbo_data.teams))
    except Exception as e:
        logger.warning("KBO data load failed (predictions disabled): %s", e)
    try:
        npb_data = build_npb_data()
        logger.info("NPB data loaded: %d teams", len(npb_data.teams))
    except Exception as e:
        logger.warning("NPB data load failed (predictions disabled): %s", e)

    _predictor = MultiLeaguePredictor(data, kbo_data, npb_data)
    _store = PredictionStore()
    _manager_store = ManagerStore()

    # 기존 예측에 닉네임 채우기 (1회성 마이그레이션)
    _backfill_nicknames()

    logger.info("Daily prediction module initialized (MLB + KBO + NPB)")


# ── Pydantic Models ──────────────────────────────────────

class GameCardResponse(BaseModel):
    game_id: int | str
    league_id: str = "mlb"
    game_date: str
    game_time: str
    game_datetime_utc: str = ""  # ISO 8601 UTC
    away_team_id: str
    home_team_id: str
    away_starter_name: str
    home_starter_name: str
    venue: str
    status: str

    game_type: str = "R"  # "R" = Regular, "S" = Spring Training

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

    # 엔진 예측 유무
    has_prediction: bool = False

    # 사용자 예측 (있으면)
    user_prediction: Optional[dict] = None


class PredictionRequest(BaseModel):
    game_id: int | str
    game_date: str
    predicted_winner: str  # "away" | "home"
    predicted_away_score: Optional[int] = None
    predicted_home_score: Optional[int] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    manager_id: Optional[str] = None
    manager_nickname: Optional[str] = None


class PredictionUpdateRequest(BaseModel):
    game_date: str
    predicted_winner: Optional[str] = None
    predicted_away_score: Optional[int] = None
    predicted_home_score: Optional[int] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class ResultCardResponse(BaseModel):
    game_id: int | str
    league_id: str = "mlb"
    game_date: str
    away_team_id: str
    home_team_id: str
    actual_away_score: int
    actual_home_score: int
    actual_winner: str
    game_type: str = "R"

    # linescore
    away_innings: list[int] = []
    home_innings: list[int] = []
    away_hits: int = 0
    home_hits: int = 0
    away_errors: int = 0
    home_errors: int = 0

    # decisions
    winning_pitcher: str = ""
    losing_pitcher: str = ""
    save_pitcher: str = ""
    away_starter_name: str = ""
    home_starter_name: str = ""

    # scoring plays + box score
    scoring_plays: list[dict] = []
    away_batters: list[dict] = []
    home_batters: list[dict] = []
    away_pitchers: list[dict] = []
    home_pitchers: list[dict] = []

    # 엔진 예측
    engine_away_win_pct: float = 0.5
    engine_pick: str = ""

    # 사용자 예측
    user_prediction: Optional[dict] = None
    user_correct: Optional[bool] = None
    engine_correct: Optional[bool] = None

    # 채점
    score_breakdown: Optional[dict] = None


class SeasonStats(BaseModel):
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


class MyStatsResponse(SeasonStats):
    spring_training: Optional[SeasonStats] = None


# ── Helpers ──────────────────────────────────────────────


def _league_date(user_now_utc: datetime, league_tz: ZoneInfo) -> date:
    """Convert UTC time to league-local date, using 06:00 boundary.

    If the league-local hour is < 6, we consider it still "yesterday" so
    late-night games are grouped with the same league-local date.
    """
    league_now = user_now_utc.astimezone(league_tz)
    if league_now.hour < 6:
        return (league_now - timedelta(days=1)).date()
    return league_now.date()


def _user_local_date(user_now_utc: datetime, user_tz_name: str) -> date:
    """Derive the user's local date from UTC + their timezone string."""
    try:
        user_tz = ZoneInfo(user_tz_name)
    except (KeyError, Exception):
        user_tz = LEAGUE_TZS["mlb"]  # fallback to ET
    return user_now_utc.astimezone(user_tz).date()


def _fetch_games_per_league(user_now_utc: datetime) -> list[DailyGame]:
    """Fetch games for each league using the league-appropriate date."""
    all_games: list[DailyGame] = []

    if _pipeline:
        mlb_date = _league_date(user_now_utc, LEAGUE_TZS["mlb"])
        try:
            all_games.extend(_pipeline.fetch_games(mlb_date))
        except Exception as e:
            logger.warning("MLB fetch failed: %s", e)

    if _kbo_pipeline:
        kbo_date = _league_date(user_now_utc, LEAGUE_TZS["kbo"])
        try:
            all_games.extend(_kbo_pipeline.fetch_games(kbo_date))
        except Exception as e:
            logger.warning("KBO fetch failed: %s", e)

    if _npb_pipeline:
        npb_date = _league_date(user_now_utc, LEAGUE_TZS["npb"])
        try:
            all_games.extend(_npb_pipeline.fetch_games(npb_date))
        except Exception as e:
            logger.warning("NPB fetch failed: %s", e)

    return all_games


def _fetch_results_per_league(user_now_utc: datetime) -> list:
    """Fetch yesterday's results for each league using league-appropriate dates."""
    from daily.pipelines.base import DailyResult
    all_results: list[DailyResult] = []

    if _pipeline:
        mlb_yesterday = _league_date(user_now_utc, LEAGUE_TZS["mlb"]) - timedelta(days=1)
        try:
            all_results.extend(_pipeline.fetch_results(mlb_yesterday))
        except Exception as e:
            logger.warning("MLB results fetch failed: %s", e)

    if _kbo_pipeline:
        kbo_yesterday = _league_date(user_now_utc, LEAGUE_TZS["kbo"]) - timedelta(days=1)
        try:
            all_results.extend(_kbo_pipeline.fetch_results(kbo_yesterday))
        except Exception as e:
            logger.warning("KBO results fetch failed: %s", e)

    if _npb_pipeline:
        npb_yesterday = _league_date(user_now_utc, LEAGUE_TZS["npb"]) - timedelta(days=1)
        try:
            all_results.extend(_npb_pipeline.fetch_results(npb_yesterday))
        except Exception as e:
            logger.warning("NPB results fetch failed: %s", e)

    return all_results


def _fetch_all_games(target_date: date) -> list[DailyGame]:
    """모든 리그의 경기를 수집."""
    all_games: list[DailyGame] = []

    if _pipeline:
        try:
            all_games.extend(_pipeline.fetch_games(target_date))
        except Exception as e:
            logger.warning("MLB fetch failed: %s", e)

    if _kbo_pipeline:
        try:
            all_games.extend(_kbo_pipeline.fetch_games(target_date))
        except Exception as e:
            logger.warning("KBO fetch failed: %s", e)

    if _npb_pipeline:
        try:
            all_games.extend(_npb_pipeline.fetch_games(target_date))
        except Exception as e:
            logger.warning("NPB fetch failed: %s", e)

    return all_games


def _fetch_all_results(target_date: date) -> list:
    """모든 리그의 결과를 수집."""
    from daily.pipelines.base import DailyResult
    all_results: list[DailyResult] = []

    if _pipeline:
        try:
            all_results.extend(_pipeline.fetch_yesterday_results()
                               if target_date == date.today() - timedelta(days=1)
                               else [])
        except Exception as e:
            logger.warning("MLB results fetch failed: %s", e)

    if _kbo_pipeline:
        try:
            all_results.extend(_kbo_pipeline.fetch_results(target_date))
        except Exception as e:
            logger.warning("KBO results fetch failed: %s", e)

    if _npb_pipeline:
        try:
            all_results.extend(_npb_pipeline.fetch_results(target_date))
        except Exception as e:
            logger.warning("NPB results fetch failed: %s", e)

    return all_results


# ── Endpoints ────────────────────────────────────────────

@router.get("/games/today")
def get_today_games(
    manager_id: Optional[str] = Query(None),
    tz: Optional[str] = Query(None, description="User IANA timezone, e.g. 'Asia/Seoul'"),
) -> list[GameCardResponse]:
    """오늘 경기 스케줄 — 모든 리그 (시뮬레이션 없이 빠르게 반환)."""
    if _pipeline is None or _store is None:
        raise HTTPException(500, "Daily module not initialized")

    user_now_utc = datetime.now(timezone.utc)
    user_tz_name = tz or "America/New_York"
    today_str = _user_local_date(user_now_utc, user_tz_name).isoformat()
    games = _fetch_games_per_league(user_now_utc)

    if not games:
        return []

    # 캐시된 예측이 있으면 포함, 없으면 예측 없이 반환
    pred_map = {}
    if today_str in _prediction_cache:
        pred_map = {p.game_id: p for p in _prediction_cache[today_str]}

    all_user_preds = _store.get_by_date(today_str)
    if manager_id is not None:
        all_user_preds = [p for p in all_user_preds if p.manager_id == manager_id]
    user_preds = {p.game_id: p for p in all_user_preds}

    return [_build_game_card(game, pred_map.get(game.game_id), user_preds.get(game.game_id)) for game in games]


@router.get("/games/{target_date}")
def get_games_by_date(target_date: str, manager_id: Optional[str] = Query(None)) -> list[GameCardResponse]:
    """특정 날짜 경기 스케줄 — 모든 리그."""
    if _pipeline is None or _store is None:
        raise HTTPException(500, "Daily module not initialized")

    try:
        dt = date.fromisoformat(target_date)
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD")

    games = _fetch_all_games(dt)
    if not games:
        return []

    pred_map = {}
    if target_date in _prediction_cache:
        pred_map = {p.game_id: p for p in _prediction_cache[target_date]}

    all_user_preds = _store.get_by_date(target_date)
    if manager_id is not None:
        all_user_preds = [p for p in all_user_preds if p.manager_id == manager_id]
    user_preds = {p.game_id: p for p in all_user_preds}

    return [_build_game_card(game, pred_map.get(game.game_id), user_preds.get(game.game_id)) for game in games]


@router.post("/games/{game_id}/predict")
def predict_single_game(game_id: str, game_date: str = Query(...)) -> GameCardResponse:
    """단일 경기 엔진 예측 (on-demand). MLB/KBO/NPB 지원."""
    if _pipeline is None or _predictor is None:
        raise HTTPException(500, "Daily module not initialized")

    try:
        dt = date.fromisoformat(game_date)
    except ValueError:
        raise HTTPException(400, "Invalid date format")

    # game_id를 int로 변환 시도 (MLB은 int, KBO/NPB는 string)
    try:
        gid: int | str = int(game_id)
    except ValueError:
        gid = game_id

    games = _fetch_all_games(dt)
    game = next((g for g in games if g.game_id == gid), None)
    if game is None:
        raise HTTPException(404, f"Game {game_id} not found on {game_date}")

    # 예측 가능 여부 확인
    if not _predictor.can_predict(game):
        return _build_game_card(game, None, None)

    # 캐시 확인
    if game_date in _prediction_cache:
        cached = {p.game_id: p for p in _prediction_cache[game_date]}
        if gid in cached:
            return _build_game_card(game, cached[gid], None)

    # 단일 경기 시뮬레이션
    pred = _predictor.predict_game(game, n_sims=200)

    # 캐시에 추가
    if game_date not in _prediction_cache:
        _prediction_cache[game_date] = []
    _prediction_cache[game_date] = [p for p in _prediction_cache[game_date] if p.game_id != gid]
    _prediction_cache[game_date].append(pred)

    return _build_game_card(game, pred, None)


def _build_game_card(game: DailyGame, pred, up) -> GameCardResponse:
    """DailyGame + prediction + user prediction → GameCardResponse."""
    return GameCardResponse(
        game_id=game.game_id,
        league_id=getattr(game, "league_id", "mlb"),
        game_date=game.game_date,
        game_time=game.game_time,
        game_datetime_utc=game.game_datetime_utc,
        away_team_id=game.away_team_id,
        home_team_id=game.home_team_id,
        away_starter_name=game.away_starter_name,
        home_starter_name=game.home_starter_name,
        venue=game.venue,
        status=game.status,
        game_type=game.game_type,
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
        has_prediction=pred is not None,
    )


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

    games = _fetch_all_games(dt)
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
            game_type=game.game_type,
            manager_id=req.manager_id or "",
            manager_nickname=_resolve_nickname(req.manager_id),
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
def get_yesterday_results(
    manager_id: Optional[str] = Query(None),
    tz: Optional[str] = Query(None, description="User IANA timezone, e.g. 'Asia/Seoul'"),
) -> list[ResultCardResponse]:
    """어제 결과 + 내 예측 비교 — 모든 리그."""
    if _pipeline is None or _store is None:
        raise HTTPException(500, "Daily module not initialized")

    user_now_utc = datetime.now(timezone.utc)
    user_tz_name = tz or "America/New_York"
    yesterday_str = (_user_local_date(user_now_utc, user_tz_name) - timedelta(days=1)).isoformat()

    results = _fetch_results_per_league(user_now_utc)
    all_user_preds = _store.get_by_date(yesterday_str)
    if manager_id is not None:
        all_user_preds = [p for p in all_user_preds if p.manager_id == manager_id]
    user_preds = {p.game_id: p for p in all_user_preds}

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
    all_user_preds = _store.get_by_date(yesterday_str)
    if manager_id is not None:
        all_user_preds = [p for p in all_user_preds if p.manager_id == manager_id]
    user_preds = {p.game_id: p for p in all_user_preds}

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
            league_id=getattr(r, "league_id", "mlb"),
            game_date=r.game_date,
            away_team_id=r.away_team_id,
            home_team_id=r.home_team_id,
            actual_away_score=r.away_score,
            actual_home_score=r.home_score,
            actual_winner=r.winner,
            game_type=r.game_type,
            away_innings=r.away_innings,
            home_innings=r.home_innings,
            away_hits=r.away_hits,
            home_hits=r.home_hits,
            away_errors=r.away_errors,
            home_errors=r.home_errors,
            winning_pitcher=r.winning_pitcher,
            losing_pitcher=r.losing_pitcher,
            save_pitcher=r.save_pitcher,
            away_starter_name=r.away_starter_name,
            home_starter_name=r.home_starter_name,
            scoring_plays=r.scoring_plays,
            away_batters=r.away_batters,
            home_batters=r.home_batters,
            away_pitchers=r.away_pitchers,
            home_pitchers=r.home_pitchers,
            engine_away_win_pct=engine_away_pct,
            engine_pick=engine_pick,
            user_prediction=asdict(up) if up else None,
            user_correct=up.correct if up else None,
            engine_correct=engine_correct,
            score_breakdown=score_bd,
        ))

    return response


@router.get("/my-stats")
def get_my_stats(manager_id: Optional[str] = Query(None)) -> MyStatsResponse:
    """내 누적 성적."""
    if _store is None:
        raise HTTPException(500, "Daily module not initialized")

    def _to_season_stats(s) -> dict:
        return dict(
            total_predictions=s.total_predictions,
            total_scored=s.total_scored,
            wins_correct=s.wins_correct,
            wins_total=s.wins_total,
            win_accuracy=s.win_accuracy,
            exact_scores=s.exact_scores,
            total_points=s.total_points,
            avg_points=s.avg_points,
            total_winner_points=s.total_winner_points,
            total_score_points=s.total_score_points,
            total_calibration_points=s.total_calibration_points,
            engine_correct=s.engine_correct,
            engine_total=s.engine_total,
            engine_accuracy=s.engine_accuracy,
        )

    regular = _store.get_cumulative_stats(manager_id=manager_id, game_type="R")
    spring = _store.get_cumulative_stats(manager_id=manager_id, game_type="S")

    resp = _to_season_stats(regular)
    if spring.total_scored > 0:
        resp["spring_training"] = _to_season_stats(spring)

    return MyStatsResponse(**resp)


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


# ── Manager Endpoints ────────────────────────────────────

class ManagerRegisterRequest(BaseModel):
    nickname: str


@router.post("/managers/register")
def register_manager(req: ManagerRegisterRequest) -> dict:
    """새 감독 등록."""
    if _manager_store is None:
        raise HTTPException(500, "Daily module not initialized")

    try:
        mgr = _manager_store.register(req.nickname)
        return {"manager_id": mgr.manager_id, "nickname": mgr.nickname}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/managers/{manager_id}")
def get_manager(manager_id: str) -> dict:
    """감독 정보 조회."""
    if _manager_store is None:
        raise HTTPException(500, "Daily module not initialized")

    mgr = _manager_store.get(manager_id)
    if mgr is None:
        raise HTTPException(404, f"Manager {manager_id} not found")
    return {"manager_id": mgr.manager_id, "nickname": mgr.nickname, "created_at": mgr.created_at}


@router.get("/leaderboard")
def get_leaderboard() -> list[dict]:
    """감독 리더보드."""
    if _store is None or _manager_store is None:
        raise HTTPException(500, "Daily module not initialized")

    return _store.get_leaderboard(_manager_store)


@router.get("/debug/managers")
def debug_managers() -> dict:
    """디버그: 매니저 스토어 + 예측 데이터 상태 확인."""
    if _store is None or _manager_store is None:
        raise HTTPException(500, "Not initialized")

    managers = _manager_store.get_all()
    pred_manager_ids = set()
    pred_nicknames = {}
    for dk in _store._all_date_keys():
        for p in _store._load_date(dk):
            mid = p.get("manager_id", "")
            if mid:
                pred_manager_ids.add(mid)
                pred_nicknames[mid] = p.get("manager_nickname", "")

    return {
        "registered_managers": [{"id": m.manager_id, "nickname": m.nickname} for m in managers],
        "prediction_manager_ids": list(pred_manager_ids),
        "prediction_nicknames": pred_nicknames,
    }


def _backfill_nicknames() -> None:
    """기존 예측에 manager_nickname이 빠진 경우 채우기."""
    if not _store or not _manager_store:
        return
    for date_key in _store._all_date_keys():
        predictions = _store._load_date(date_key)
        changed = False
        for p in predictions:
            mid = p.get("manager_id", "")
            if mid and not p.get("manager_nickname"):
                mgr = _manager_store.get(mid)
                if mgr:
                    p["manager_nickname"] = mgr.nickname
                    changed = True
        if changed:
            _store._save_date(date_key, predictions)
            logger.info("Backfilled nicknames for %s", date_key)


def _resolve_nickname(manager_id: str | None) -> str:
    """manager_id로 닉네임 조회. 없으면 빈 문자열."""
    if not manager_id or not _manager_store:
        return ""
    mgr = _manager_store.get(manager_id)
    return mgr.nickname if mgr else ""


def _is_locked(game: DailyGame) -> bool:
    """경기 시작 1시간 전이면 마감."""
    # 이미 진행중이거나 종료된 경기는 마감
    if game.status in ("In Progress", "Final", "Game Over", "Completed Early"):
        return True

    if not game.game_datetime_utc:
        return False

    try:
        game_dt = datetime.fromisoformat(game.game_datetime_utc.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return now >= game_dt - timedelta(hours=1)
    except (ValueError, TypeError):
        return False
