"""예측 채점 시스템.

채점 기준 (총 100점):
- 승패 적중: 50점
- 점수 정확도: 0~40점 (각 팀 오차 기반) + 정확한 스코어 보너스 +10
- 승률 칼리브레이션: 0~10점 (Brier score 기반)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScoreBreakdown:
    """채점 상세."""
    winner_points: int = 0        # 0 or 50
    score_points: float = 0.0     # 0~40
    exact_score_bonus: int = 0    # 0 or 10
    calibration_points: float = 0.0  # 0~10
    total: float = 0.0


def calculate_prediction_score(
    predicted_winner: str,
    actual_winner: str,
    predicted_away_score: int | None,
    predicted_home_score: int | None,
    actual_away_score: int,
    actual_home_score: int,
    predicted_win_pct: float | None = None,
) -> ScoreBreakdown:
    """단일 예측 채점.

    Args:
        predicted_winner: "away" or "home"
        actual_winner: "away" or "home"
        predicted_away_score: 예측한 원정팀 점수 (optional)
        predicted_home_score: 예측한 홈팀 점수 (optional)
        actual_away_score: 실제 원정팀 점수
        actual_home_score: 실제 홈팀 점수
        predicted_win_pct: 예측 승률 (0~1, optional)

    Returns:
        ScoreBreakdown with detailed scoring
    """
    breakdown = ScoreBreakdown()

    # 1. 승패 적중 (50점)
    if predicted_winner == actual_winner:
        breakdown.winner_points = 50

    # 2. 점수 정확도 (0~40점)
    if predicted_away_score is not None and predicted_home_score is not None:
        away_diff = abs(predicted_away_score - actual_away_score)
        home_diff = abs(predicted_home_score - actual_home_score)
        total_diff = away_diff + home_diff

        # 점수 오차 → 점수 변환 (최대 40점)
        # 오차 0: 40점, 오차 1: 35점, 오차 2: 28점, ...
        # 공식: max(0, 40 - total_diff^1.5 * 5)
        score_pts = max(0.0, 40.0 - (total_diff ** 1.5) * 5.0)
        breakdown.score_points = round(score_pts, 1)

        # 정확한 스코어 보너스
        if away_diff == 0 and home_diff == 0:
            breakdown.exact_score_bonus = 10

    # 3. 승률 칼리브레이션 (0~10점, Brier score 기반)
    if predicted_win_pct is not None:
        # predicted_win_pct is P(predicted_winner wins)
        # Brier: (p - actual)^2, actual = 1 if correct, 0 if wrong
        actual_outcome = 1.0 if predicted_winner == actual_winner else 0.0
        brier = (predicted_win_pct - actual_outcome) ** 2

        # Brier 0 → 10점, Brier 0.25 (random) → 5점, Brier 1 → 0점
        cal_pts = max(0.0, 10.0 * (1.0 - brier / 0.5))
        breakdown.calibration_points = round(cal_pts, 1)

    breakdown.total = (
        breakdown.winner_points
        + breakdown.score_points
        + breakdown.exact_score_bonus
        + breakdown.calibration_points
    )

    return breakdown


@dataclass
class CumulativeStats:
    """누적 성적."""
    total_predictions: int = 0
    total_scored: int = 0  # 결과 나온 예측 수
    wins_correct: int = 0
    wins_total: int = 0
    exact_scores: int = 0
    total_points: float = 0.0
    total_winner_points: int = 0
    total_score_points: float = 0.0
    total_calibration_points: float = 0.0

    # 엔진 비교
    engine_correct: int = 0
    engine_total: int = 0

    @property
    def win_accuracy(self) -> float:
        return self.wins_correct / self.wins_total if self.wins_total > 0 else 0.0

    @property
    def avg_points(self) -> float:
        return self.total_points / self.total_scored if self.total_scored > 0 else 0.0

    @property
    def engine_accuracy(self) -> float:
        return self.engine_correct / self.engine_total if self.engine_total > 0 else 0.0
