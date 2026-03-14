"""로지스틱 수축 — 경기별 승률 예측의 과신 보정.

시뮬레이션 결과의 away_win_pct를 50% 방향으로 수축하여
칼리브레이션을 개선. 기존 시뮬레이션 코드는 수정하지 않음.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from data.schedule import GameRecord


def shrink_probability(p: float, shrink: float) -> float:
    """단일 확률값에 로지스틱 수축 적용.

    Args:
        p: 원래 승률 (0~1)
        shrink: 수축 계수 (0=전부 50%, 1=수축 없음)
    """
    eps = 1e-15
    p = max(eps, min(1 - eps, p))
    log_odds = math.log(p / (1 - p))
    adjusted = shrink * log_odds
    return 1.0 / (1.0 + math.exp(-adjusted))


def apply_shrinkage(
    games: list[GameRecord],
    shrink: float,
) -> list[GameRecord]:
    """경기 리스트의 sim_away_win_pct에 수축 적용.

    원본을 수정하지 않고 새 리스트를 반환.
    """
    from dataclasses import replace

    result = []
    for g in games:
        if g.sim_away_win_pct is None:
            result.append(g)
            continue
        adjusted_pct = shrink_probability(g.sim_away_win_pct, shrink)
        new_g = replace(g, sim_away_win_pct=adjusted_pct)
        result.append(new_g)
    return result


def compute_metrics(games: list[GameRecord]) -> dict[str, float]:
    """경기 리스트에서 L3 메트릭 산출."""
    predictions = []
    outcomes = []
    for g in games:
        if g.sim_away_win_pct is None or g.away_score is None or g.home_score is None:
            continue
        predictions.append(g.sim_away_win_pct)
        outcomes.append(1.0 if g.away_score > g.home_score else 0.0)

    pred = np.array(predictions)
    actual = np.array(outcomes)

    # Brier
    brier = float(np.mean((pred - actual) ** 2))

    # Log Loss
    eps = 1e-15
    p_clip = np.clip(pred, eps, 1 - eps)
    ll = -float(np.mean(actual * np.log(p_clip) + (1 - actual) * np.log(1 - p_clip)))

    # AUC (Mann-Whitney U)
    pos = pred[actual == 1]
    neg = pred[actual == 0]
    if len(pos) > 0 and len(neg) > 0:
        u = 0.0
        for p in pos:
            u += np.sum(p > neg) + 0.5 * np.sum(p == neg)
        auc = float(u / (len(pos) * len(neg)))
    else:
        auc = 0.5

    return {"brier": brier, "log_loss": ll, "auc": auc, "n": len(pred)}


def grid_search_shrinkage(
    games: list[GameRecord],
    shrink_values: list[float] | None = None,
) -> list[dict]:
    """그리드 서치로 각 shrink 값의 메트릭 산출.

    Returns:
        [{shrink, brier, log_loss, auc, n}, ...]
    """
    if shrink_values is None:
        shrink_values = [round(0.50 + 0.05 * i, 2) for i in range(9)]

    results = []
    for s in shrink_values:
        adjusted = apply_shrinkage(games, s)
        metrics = compute_metrics(adjusted)
        metrics["shrink"] = s
        results.append(metrics)

    return results
