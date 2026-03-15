"""예측 저장소 — Upstash Redis (우선) / JSON 파일 폴백 + 채점."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .redis_client import UpstashRedis, is_redis_available
from .scoring import ScoreBreakdown, CumulativeStats, calculate_prediction_score

logger = logging.getLogger(__name__)


@dataclass
class UserPrediction:
    """사용자 예측."""
    prediction_id: str
    game_id: int
    game_date: str
    away_team_id: str
    home_team_id: str
    predicted_winner: str  # "away" | "home"
    predicted_away_score: Optional[int] = None
    predicted_home_score: Optional[int] = None
    confidence: Optional[float] = None  # 0.0 - 1.0
    created_at: str = ""
    updated_at: str = ""
    locked: bool = False
    game_type: str = "R"  # "R" = Regular, "S" = Spring Training
    manager_id: str = ""  # 감독 ID (빈 문자열 = 미지정)

    # 실제 결과 (나중에 채워짐)
    actual_winner: Optional[str] = None
    actual_away_score: Optional[int] = None
    actual_home_score: Optional[int] = None
    correct: Optional[bool] = None

    # 채점 결과
    score_total: Optional[float] = None
    score_winner: Optional[int] = None
    score_accuracy: Optional[float] = None
    score_exact_bonus: Optional[int] = None
    score_calibration: Optional[float] = None


class PredictionStore:
    """예측 저장소 — Redis 우선, JSON 폴백."""

    def __init__(self, store_dir: str = "data/predictions/"):
        self._store_dir = Path(store_dir)
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._redis: UpstashRedis | None = None
        if is_redis_available():
            try:
                self._redis = UpstashRedis()
                logger.info("PredictionStore: using Upstash Redis")
            except Exception as e:
                logger.warning("Redis init failed, falling back to JSON: %s", e)
        else:
            logger.info("PredictionStore: using JSON file storage")

    def _redis_key(self, game_date: str) -> str:
        return f"pred:{game_date}"

    def _date_path(self, game_date: str) -> Path:
        return self._store_dir / f"{game_date}.json"

    def _load_date(self, game_date: str) -> list[dict]:
        if self._redis:
            data = self._redis.get_json(self._redis_key(game_date))
            return data if data else []
        path = self._date_path(game_date)
        if not path.exists():
            return []
        with open(path) as f:
            return json.load(f)

    def _save_date(self, game_date: str, predictions: list[dict]) -> None:
        if self._redis:
            self._redis.set_json(self._redis_key(game_date), predictions)
            return
        path = self._date_path(game_date)
        with open(path, "w") as f:
            json.dump(predictions, f, indent=2)

    def _all_date_keys(self) -> list[str]:
        """모든 날짜 키 목록."""
        if self._redis:
            keys = self._redis.keys("pred:*")
            return [k.replace("pred:", "") for k in keys]
        return [p.stem for p in self._store_dir.glob("*.json") if p.name != "stats.json"]

    def submit(
        self,
        game_id: int,
        game_date: str,
        away_team_id: str,
        home_team_id: str,
        predicted_winner: str,
        predicted_away_score: int | None = None,
        predicted_home_score: int | None = None,
        confidence: float | None = None,
        game_type: str = "R",
        manager_id: str = "",
    ) -> UserPrediction:
        """예측 제출."""
        predictions = self._load_date(game_date)

        # 이미 해당 경기에 예측이 있으면 에러
        for p in predictions:
            if p["game_id"] == game_id and p.get("manager_id", "") == manager_id:
                if p.get("locked"):
                    raise ValueError(f"Prediction for game {game_id} is locked")
                raise ValueError(f"Prediction already exists for game {game_id}. Use update.")

        now = datetime.utcnow().isoformat()
        pred = UserPrediction(
            prediction_id=str(uuid.uuid4())[:8],
            game_id=game_id,
            game_date=game_date,
            away_team_id=away_team_id,
            home_team_id=home_team_id,
            predicted_winner=predicted_winner,
            predicted_away_score=predicted_away_score,
            predicted_home_score=predicted_home_score,
            confidence=confidence,
            created_at=now,
            updated_at=now,
            game_type=game_type,
            manager_id=manager_id,
        )

        predictions.append(asdict(pred))
        self._save_date(game_date, predictions)
        logger.info("Prediction submitted: %s for game %d", pred.prediction_id, game_id)
        return pred

    def update(
        self,
        prediction_id: str,
        game_date: str,
        predicted_winner: str | None = None,
        predicted_away_score: int | None = None,
        predicted_home_score: int | None = None,
        confidence: float | None = None,
    ) -> UserPrediction:
        """예측 수정."""
        predictions = self._load_date(game_date)

        for p in predictions:
            if p["prediction_id"] == prediction_id:
                if p.get("locked"):
                    raise ValueError("Prediction is locked")
                if predicted_winner is not None:
                    p["predicted_winner"] = predicted_winner
                if predicted_away_score is not None:
                    p["predicted_away_score"] = predicted_away_score
                if predicted_home_score is not None:
                    p["predicted_home_score"] = predicted_home_score
                if confidence is not None:
                    p["confidence"] = confidence
                p["updated_at"] = datetime.utcnow().isoformat()
                self._save_date(game_date, predictions)
                return UserPrediction(**p)

        raise ValueError(f"Prediction {prediction_id} not found")

    def get_by_date(self, game_date: str) -> list[UserPrediction]:
        """특정 날짜의 모든 예측 조회."""
        predictions = self._load_date(game_date)
        return [UserPrediction(**p) for p in predictions]

    def get_by_id(self, prediction_id: str, game_date: str) -> UserPrediction | None:
        """예측 ID로 조회."""
        for p in self._load_date(game_date):
            if p["prediction_id"] == prediction_id:
                return UserPrediction(**p)
        return None

    def lock_game(self, game_id: int, game_date: str) -> None:
        """경기 예측 마감 (lock)."""
        predictions = self._load_date(game_date)
        changed = False
        for p in predictions:
            if p["game_id"] == game_id and not p.get("locked"):
                p["locked"] = True
                changed = True
        if changed:
            self._save_date(game_date, predictions)

    def record_results(
        self,
        game_id: int,
        game_date: str,
        actual_winner: str,
        actual_away_score: int,
        actual_home_score: int,
        engine_win_pct: float | None = None,
    ) -> ScoreBreakdown | None:
        """실제 결과 기록 + 자동 채점."""
        predictions = self._load_date(game_date)
        result_breakdown = None
        changed = False
        for p in predictions:
            if p["game_id"] == game_id:
                p["actual_winner"] = actual_winner
                p["actual_away_score"] = actual_away_score
                p["actual_home_score"] = actual_home_score
                p["correct"] = (p["predicted_winner"] == actual_winner)

                # 채점
                breakdown = calculate_prediction_score(
                    predicted_winner=p["predicted_winner"],
                    actual_winner=actual_winner,
                    predicted_away_score=p.get("predicted_away_score"),
                    predicted_home_score=p.get("predicted_home_score"),
                    actual_away_score=actual_away_score,
                    actual_home_score=actual_home_score,
                    predicted_win_pct=p.get("confidence"),
                )
                p["score_total"] = breakdown.total
                p["score_winner"] = breakdown.winner_points
                p["score_accuracy"] = breakdown.score_points
                p["score_exact_bonus"] = breakdown.exact_score_bonus
                p["score_calibration"] = breakdown.calibration_points
                result_breakdown = breakdown
                changed = True
        if changed:
            self._save_date(game_date, predictions)
        return result_breakdown

    def get_cumulative_stats(
        self,
        manager_id: str | None = None,
        game_type: str | None = "R",
    ) -> CumulativeStats:
        """누적 성적 계산.

        Args:
            manager_id: 특정 감독의 성적만 조회. None이면 전체.
            game_type: "R"=정규시즌, "S"=시범경기, None=전체.
        """
        stats = CumulativeStats()

        for date_key in sorted(self._all_date_keys()):
            predictions = self._load_date(date_key)
            for p in predictions:
                # 감독 필터
                if manager_id is not None and p.get("manager_id", "") != manager_id:
                    continue
                # game_type 필터
                if game_type is not None and p.get("game_type", "R") != game_type:
                    continue
                stats.total_predictions += 1
                if p.get("actual_winner") is not None:
                    stats.total_scored += 1
                    stats.wins_total += 1
                    if p.get("correct"):
                        stats.wins_correct += 1
                    if p.get("score_exact_bonus", 0) > 0:
                        stats.exact_scores += 1
                    stats.total_points += p.get("score_total", 0)
                    stats.total_winner_points += p.get("score_winner", 0)
                    stats.total_score_points += p.get("score_accuracy", 0)
                    stats.total_calibration_points += p.get("score_calibration", 0)

        return stats

    def get_leaderboard(self, manager_store) -> list[dict]:
        """전체 감독 리더보드.

        정규시즌 결과가 있으면 정규시즌만, 없으면 시범경기로 표시.

        Args:
            manager_store: ManagerStore instance to get manager info.

        Returns:
            Sorted list of dicts with manager stats, by avg_points descending.
            "season" field: "R" or "S".
        """
        managers = manager_store.get_all()

        # 정규시즌 결과가 하나라도 있는지 확인
        regular_any = self.get_cumulative_stats(game_type="R")
        use_type = "R" if regular_any.total_scored > 0 else "S"

        # 등록된 감독 ID → nickname 매핑
        mgr_map = {mgr.manager_id: mgr.nickname for mgr in managers}

        # 모든 예측에서 고유 manager_id 수집 (빈 문자열 포함)
        all_manager_ids: set[str] = set()
        for date_key in self._all_date_keys():
            for p in self._load_date(date_key):
                mid = p.get("manager_id", "")
                all_manager_ids.add(mid)

        leaderboard = []
        for mid in all_manager_ids:
            stats = self.get_cumulative_stats(manager_id=mid, game_type=use_type)
            if stats.total_scored < 1:
                continue
            # 닉네임: 등록된 감독이면 닉네임, 아니면 "Anonymous"
            nickname = mgr_map.get(mid, "Anonymous" if not mid else mid[:8])
            leaderboard.append({
                "manager_id": mid,
                "nickname": nickname,
                "total_scored": stats.total_scored,
                "wins_correct": stats.wins_correct,
                "wins_total": stats.wins_total,
                "win_accuracy": stats.win_accuracy,
                "avg_points": stats.avg_points,
                "total_points": stats.total_points,
                "exact_scores": stats.exact_scores,
                "season": use_type,
            })

        leaderboard.sort(key=lambda x: x["avg_points"], reverse=True)
        return leaderboard

    def get_date_results(self, game_date: str) -> list[dict]:
        """특정 날짜의 채점 상세 결과."""
        predictions = self._load_date(game_date)
        results = []
        for p in predictions:
            if p.get("actual_winner") is not None:
                results.append({
                    "prediction_id": p["prediction_id"],
                    "game_id": p["game_id"],
                    "away_team_id": p["away_team_id"],
                    "home_team_id": p["home_team_id"],
                    "predicted_winner": p["predicted_winner"],
                    "predicted_away_score": p.get("predicted_away_score"),
                    "predicted_home_score": p.get("predicted_home_score"),
                    "actual_winner": p["actual_winner"],
                    "actual_away_score": p["actual_away_score"],
                    "actual_home_score": p["actual_home_score"],
                    "correct": p["correct"],
                    "score_total": p.get("score_total", 0),
                    "score_winner": p.get("score_winner", 0),
                    "score_accuracy": p.get("score_accuracy", 0),
                    "score_exact_bonus": p.get("score_exact_bonus", 0),
                    "score_calibration": p.get("score_calibration", 0),
                })
        return results
