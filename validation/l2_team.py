"""L2: 경기 시뮬레이션 검증 — 팀별 득점 비교."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from engine.models import LeagueStats, ParkFactors, PitcherStats, Team
from engine.monte_carlo import simulate_series
from .ground_truth import ActualResults

logger = logging.getLogger(__name__)


@dataclass
class L2Result:
    n_teams: int
    runs_corr: float
    runs_rmse: float
    mean_sim_runs: float
    mean_actual_runs: float
    scoring_bias: float  # sim - actual (양수 = 과대)
    team_details: list[dict]
    scoring_distribution: dict  # 0점이닝%, 1점이닝% 등

    def passed(self) -> dict[str, bool]:
        return {
            "runs_corr": self.runs_corr > 0.85,
            "runs_rmse": self.runs_rmse < 0.50,
        }


def run_l2(
    teams: dict[str, Team],
    league: LeagueStats,
    actual: ActualResults,
    n_sim: int = 500,
    seed: int = 42,
) -> L2Result:
    """L2 검증: 각 팀의 시뮬레이션 평균 득점 vs 실제 평균 득점."""

    # 리그 평균 상대팀 구성
    from tests.conftest import _make_batter, _make_pitcher
    avg_lineup = [_make_batter(f"avg{i}", f"Avg {i+1}",
        k_rate=league.k_rate, bb_rate=league.bb_rate, hbp_rate=league.hbp_rate,
        single_rate_bip=league.single_rate_bip, double_rate_bip=league.double_rate_bip,
        triple_rate_bip=league.triple_rate_bip, hr_rate_bip=league.hr_rate_bip,
        go_rate_bip=league.go_rate_bip, fo_rate_bip=league.fo_rate_bip,
    ) for i in range(9)]
    avg_sp = _make_pitcher("avg_sp", "Avg SP",
        k_rate=league.k_rate, bb_rate=league.bb_rate, hbp_rate=league.hbp_rate,
        hr_rate_bip=league.hr_rate_bip, go_fo_ratio=league.go_fo_ratio,
    )
    avg_bullpen = [_make_pitcher(f"avg_rp{i}", f"Avg RP {i+1}",
        k_rate=league.k_rate, bb_rate=league.bb_rate, hbp_rate=league.hbp_rate,
        hr_rate_bip=league.hr_rate_bip, go_fo_ratio=league.go_fo_ratio,
    ) for i in range(5)]
    avg_team = Team(team_id="avg", name="League Average", lineup=avg_lineup,
                    starter=avg_sp, bullpen=avg_bullpen)
    neutral_park = ParkFactors(park_name="Neutral", pf_1b=100, pf_2b=100, pf_3b=100, pf_hr=100)

    # 실제 팀 득실점 (경기 결과에서 산출)
    team_runs_scored = {}
    team_games = {}
    for g in actual.game_actuals:
        for side in ["away", "home"]:
            t = g[side]
            score_key = f"{side}_score"
            team_runs_scored.setdefault(t, 0)
            team_runs_scored[t] += g[score_key]
            team_games.setdefault(t, 0)
            team_games[t] += 1

    team_details = []
    sim_runs_list = []
    actual_runs_list = []

    rng_seed = seed
    for team_id, team in teams.items():
        if team_id not in team_runs_scored:
            continue
        actual_rpg = team_runs_scored[team_id] / team_games[team_id]

        # 팀 vs 리그 평균 시뮬레이션
        series = simulate_series(team, avg_team, neutral_park, league, n_simulations=n_sim, seed=rng_seed)
        rng_seed += 1

        sim_rpg = series.avg_away_runs

        sim_runs_list.append(sim_rpg)
        actual_runs_list.append(actual_rpg)
        team_details.append({
            "team_id": team_id,
            "name": team.name,
            "sim_rpg": sim_rpg,
            "actual_rpg": actual_rpg,
            "diff": sim_rpg - actual_rpg,
        })

    sim_arr = np.array(sim_runs_list)
    actual_arr = np.array(actual_runs_list)

    runs_corr = float(np.corrcoef(sim_arr, actual_arr)[0, 1]) if len(sim_arr) > 2 else 0.0
    runs_rmse = float(np.sqrt(np.mean((sim_arr - actual_arr) ** 2)))
    scoring_bias = float(np.mean(sim_arr - actual_arr))

    # 이닝별 득점 분포 (전체 시뮬레이션에서 추출)
    scoring_distribution = {}  # V0.1: 요약만

    result = L2Result(
        n_teams=len(team_details),
        runs_corr=runs_corr,
        runs_rmse=runs_rmse,
        mean_sim_runs=float(np.mean(sim_arr)),
        mean_actual_runs=float(np.mean(actual_arr)),
        scoring_bias=scoring_bias,
        team_details=team_details,
        scoring_distribution=scoring_distribution,
    )

    logger.info(
        "L2: n=%d teams, runs corr=%.3f, RMSE=%.2f, bias=%+.2f R/G",
        result.n_teams, runs_corr, runs_rmse, scoring_bias,
    )

    return result
