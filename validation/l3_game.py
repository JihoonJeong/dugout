"""L3: 경기 예측 검증 — 승률 예측 vs 실제 결과."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from collections import defaultdict

import numpy as np

from data.constants import TEAM_MAPPING
from engine.models import LeagueStats, ParkFactors, Team
from engine.monte_carlo import simulate_series
from .ground_truth import ActualResults

logger = logging.getLogger(__name__)


@dataclass
class L3Result:
    n_games: int
    brier_score: float
    log_loss: float
    auc_roc: float
    calibration: dict[str, dict]  # bucket → {"pred": float, "actual": float, "n": int}
    game_details: list[dict]

    def passed(self) -> dict[str, bool]:
        return {
            "brier_score": self.brier_score < 0.250,
            "log_loss": self.log_loss < 0.695,
            "auc_roc": self.auc_roc > 0.55,
        }


def run_l3(
    teams: dict[str, Team],
    parks: dict[str, ParkFactors],
    league: LeagueStats,
    actual: ActualResults,
    n_sim_per_matchup: int = 500,
    max_games: int | None = None,
    seed: int = 42,
) -> L3Result:
    """L3 검증: 경기별 승률 예측 vs 실제 결과.

    V0.1: 같은 매치업은 같은 승률을 캐싱하여 재사용.
    """
    # 매치업별 승률 캐시 (V0.1은 고정 라인업이므로 같은 팀 쌍 = 같은 승률)
    matchup_cache: dict[tuple[str, str], float] = {}

    games = actual.game_actuals
    if max_games is not None:
        # 균등 샘플링
        rng = np.random.default_rng(seed)
        indices = rng.choice(len(games), size=min(max_games, len(games)), replace=False)
        games = [games[i] for i in sorted(indices)]

    predictions = []
    outcomes = []
    game_details = []

    for g in games:
        away_id = g["away"]
        home_id = g["home"]

        if away_id not in teams or home_id not in teams:
            continue

        # 캐시에서 승률 조회 또는 시뮬레이션
        cache_key = (away_id, home_id)
        if cache_key not in matchup_cache:
            away_team = teams[away_id]
            home_team = teams[home_id]
            park_name = TEAM_MAPPING[home_id]["park"]
            park = parks.get(park_name)
            if park is None:
                park = ParkFactors(park_name=park_name, pf_1b=100, pf_2b=100, pf_3b=100, pf_hr=100)

            series = simulate_series(
                away_team, home_team, park, league,
                n_simulations=n_sim_per_matchup, seed=seed + hash(cache_key) % 10000,
            )
            matchup_cache[cache_key] = series.away_win_pct

        away_win_pct = matchup_cache[cache_key]
        actual_outcome = 1.0 if g["winner"] == "away" else 0.0

        predictions.append(away_win_pct)
        outcomes.append(actual_outcome)
        game_details.append({
            "game_id": g.get("game_id"),
            "date": g.get("date", ""),
            "away": away_id,
            "home": home_id,
            "pred_away_win": away_win_pct,
            "actual_winner": g["winner"],
        })

    pred = np.array(predictions)
    actual_arr = np.array(outcomes)

    # Brier Score
    brier = float(np.mean((pred - actual_arr) ** 2))

    # Log Loss
    eps = 1e-15
    pred_clipped = np.clip(pred, eps, 1 - eps)
    ll = -float(np.mean(actual_arr * np.log(pred_clipped) + (1 - actual_arr) * np.log(1 - pred_clipped)))

    # AUC-ROC
    auc = _compute_auc(pred, actual_arr)

    # Calibration
    calibration = _compute_calibration(pred, actual_arr)

    result = L3Result(
        n_games=len(pred),
        brier_score=brier,
        log_loss=ll,
        auc_roc=auc,
        calibration=calibration,
        game_details=game_details,
    )

    logger.info(
        "L3: n=%d games, Brier=%.4f, LogLoss=%.4f, AUC=%.3f",
        result.n_games, brier, ll, auc,
    )

    return result


def _compute_auc(pred: np.ndarray, actual: np.ndarray) -> float:
    """간단한 AUC-ROC 계산 (Mann-Whitney U statistic)."""
    pos = pred[actual == 1]
    neg = pred[actual == 0]
    if len(pos) == 0 or len(neg) == 0:
        return 0.5

    # U statistic
    n_pos = len(pos)
    n_neg = len(neg)
    u = 0.0
    for p in pos:
        u += np.sum(p > neg) + 0.5 * np.sum(p == neg)
    return float(u / (n_pos * n_neg))


def _compute_calibration(pred: np.ndarray, actual: np.ndarray, n_buckets: int = 10) -> dict:
    """예측 확률을 버킷으로 분류하여 칼리브레이션 계산."""
    buckets = {}
    edges = np.linspace(0, 1, n_buckets + 1)
    for i in range(n_buckets):
        lo, hi = edges[i], edges[i + 1]
        mask = (pred >= lo) & (pred < hi) if i < n_buckets - 1 else (pred >= lo) & (pred <= hi)
        n = int(mask.sum())
        if n == 0:
            continue
        label = f"{lo:.1f}-{hi:.1f}"
        buckets[label] = {
            "pred_mean": float(pred[mask].mean()),
            "actual_mean": float(actual[mask].mean()),
            "n": n,
        }
    return buckets
