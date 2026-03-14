"""Monte Carlo 시뮬레이션."""

import numpy as np

from .game import simulate_game
from .models import LeagueStats, ParkFactors, SeriesResult, Team


def simulate_series(
    away_team: Team,
    home_team: Team,
    park: ParkFactors,
    league: LeagueStats,
    n_simulations: int = 1000,
    seed: int = 42,
) -> SeriesResult:
    """동일 매치업을 N회 시뮬레이션하여 승률 및 통계 분포를 산출."""
    rng = np.random.default_rng(seed)
    results = []

    for _ in range(n_simulations):
        # 매 게임마다 불펜 인덱스 초기화
        away_team.reset_bullpen()
        home_team.reset_bullpen()
        result = simulate_game(away_team, home_team, park, league, rng)
        results.append(result)

    return SeriesResult(results)
