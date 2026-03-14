"""팀 기본 승률과 경기별 선발 승률의 블렌딩.

Phase 0의 팀 전력 시그널(고정 선발 = 팀 대표 에이스)과
Phase 1-A의 경기별 선발투수 시그널을 결합하여 AUC를 복원.

blended = alpha × team_base_win_pct + (1 - alpha) × game_starter_win_pct
final = shrink(blended)
"""

from __future__ import annotations

from dataclasses import replace

from data.schedule import GameRecord
from simulation.shrinkage import shrink_probability


def blend_probabilities(
    team_base: float,
    game_starter: float,
    alpha: float,
) -> float:
    """팀 기본 승률과 경기별 선발 승률을 alpha로 블렌딩."""
    return alpha * team_base + (1 - alpha) * game_starter


def apply_blending(
    phase0_games: list[GameRecord],
    phase1a_games: list[GameRecord],
    alpha: float,
    shrink: float = 1.0,
) -> list[GameRecord]:
    """Phase 0과 Phase 1-A 결과를 블렌딩 + 수축 적용.

    두 리스트는 같은 순서/같은 경기를 가정.
    원본 수정 없이 새 리스트 반환.
    """
    # game_id로 Phase 0 승률을 빠르게 lookup
    p0_map: dict[int, float] = {}
    for g in phase0_games:
        if g.sim_away_win_pct is not None:
            p0_map[g.game_id] = g.sim_away_win_pct

    result = []
    for g in phase1a_games:
        if g.sim_away_win_pct is None or g.game_id not in p0_map:
            result.append(g)
            continue

        blended = blend_probabilities(p0_map[g.game_id], g.sim_away_win_pct, alpha)

        if shrink < 1.0:
            blended = shrink_probability(blended, shrink)

        new_g = replace(g, sim_away_win_pct=blended)
        result.append(new_g)

    return result


def grid_search_blending(
    phase0_games: list[GameRecord],
    phase1a_games: list[GameRecord],
    alpha_values: list[float] | None = None,
    shrink: float = 1.0,
) -> list[dict]:
    """alpha 그리드 서치.

    Returns:
        [{alpha, brier, log_loss, auc, n}, ...]
    """
    from simulation.shrinkage import compute_metrics

    if alpha_values is None:
        alpha_values = [round(0.30 + 0.05 * i, 2) for i in range(9)]

    results = []
    for a in alpha_values:
        blended = apply_blending(phase0_games, phase1a_games, a, shrink=shrink)
        metrics = compute_metrics(blended)
        metrics["alpha"] = a
        results.append(metrics)

    return results
