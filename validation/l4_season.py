"""L4: 시즌 예측 검증 — 팀별 승수 예측.

참고: 시즌 전 프로젝션 모델(PECOTA/ZiPS)의 팀 승수 RMSE는 일반적으로 7~10 범위.
우리 엔진은 실제 로스터 기반(시즌 전 프로젝션 아님)이므로 직접 비교는 불가하지만,
이 범위를 칼리브레이션 참고로 사용.
"""

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

PYTHAGOREAN_EXP = 1.83


@dataclass
class L4Result:
    n_teams: int
    wins_rmse: float
    wins_corr: float
    playoff_correct: int
    playoff_total: int
    pythag_wins_rmse: float  # 실제 득실점 기반 피타고라스
    sim_pythag_wins_rmse: float  # 시뮬레이션 득실점 기반 피타고라스
    sim_pythag_vs_direct_rmse: float  # 엔진 피타고라스 vs 엔진 직접 시뮬레이션
    team_details: list[dict]

    def passed(self) -> dict[str, bool]:
        return {
            "wins_rmse": self.wins_rmse < 8.0,
            "wins_corr": self.wins_corr > 0.75,
            "playoff_teams": self.playoff_correct >= 8,
        }


def run_l4(
    teams: dict[str, Team],
    parks: dict[str, ParkFactors],
    league: LeagueStats,
    actual: ActualResults,
    n_sim_per_matchup: int = 200,
    seed: int = 42,
) -> L4Result:
    """L4 검증: 팀별 시즌 승수 예측 (간이 방법).

    각 팀 쌍의 승률을 산출하고, 실제 일정의 상대 팀 빈도를 가중하여 승수 추정.
    추가로 시뮬레이션 득실점 기반 피타고라스를 산출하여 "득점 예측 오류"와
    "경기 변환 손실"을 분리.
    """
    team_ids = [t for t in teams if t in actual.team_actuals]

    # 실제 경기에서 팀 쌍별 경기 수 집계
    matchup_counts = defaultdict(lambda: defaultdict(int))
    for g in actual.game_actuals:
        matchup_counts[g["away"]][g["home"]] += 1

    # 팀 쌍별 시뮬레이션 결과 저장 (승률 + 평균 득점)
    matchup_results: dict[tuple[str, str], dict] = {}
    logger.info("Simulating %d team pairs...", len(team_ids) * (len(team_ids) - 1))

    sim_seed = seed
    for away_id in team_ids:
        for home_id in team_ids:
            if away_id == home_id:
                continue
            if (away_id, home_id) in matchup_results:
                continue

            park_name = TEAM_MAPPING[home_id]["park"]
            park = parks.get(park_name, ParkFactors(park_name=park_name, pf_1b=100, pf_2b=100, pf_3b=100, pf_hr=100))

            series = simulate_series(
                teams[away_id], teams[home_id], park, league,
                n_simulations=n_sim_per_matchup, seed=sim_seed,
            )
            matchup_results[(away_id, home_id)] = {
                "away_win_pct": series.away_win_pct,
                "avg_away_runs": series.avg_away_runs,
                "avg_home_runs": series.avg_home_runs,
            }
            sim_seed += 1

    # 팀별 시즌 승수 추정 + 시뮬레이션 득실점 집계
    team_details = []
    pred_wins_list = []
    actual_wins_list = []

    # 실제 득실점 기반 피타고라스
    team_rs = defaultdict(int)
    team_ra = defaultdict(int)
    for g in actual.game_actuals:
        team_rs[g["away"]] += g["away_score"]
        team_ra[g["away"]] += g["home_score"]
        team_rs[g["home"]] += g["home_score"]
        team_ra[g["home"]] += g["away_score"]

    pythag_wins_list = []
    sim_pythag_wins_list = []

    for team_id in team_ids:
        actual_info = actual.team_actuals[team_id]
        actual_wins = actual_info["wins"]
        total_games = actual_info["games"]

        # 시뮬레이션 승수 = Σ(matchup_win_pct × games_vs_opponent)
        weighted_win_sum = 0.0
        weighted_game_sum = 0
        # 시뮬레이션 득실점 집계
        sim_rs_total = 0.0
        sim_ra_total = 0.0
        sim_games_total = 0

        for opp_id in team_ids:
            if opp_id == team_id:
                continue
            # 어웨이 게임
            n_away = matchup_counts.get(team_id, {}).get(opp_id, 0)
            if n_away > 0 and (team_id, opp_id) in matchup_results:
                mr = matchup_results[(team_id, opp_id)]
                weighted_win_sum += mr["away_win_pct"] * n_away
                weighted_game_sum += n_away
                sim_rs_total += mr["avg_away_runs"] * n_away
                sim_ra_total += mr["avg_home_runs"] * n_away
                sim_games_total += n_away

            # 홈 게임
            n_home = matchup_counts.get(opp_id, {}).get(team_id, 0)
            if n_home > 0 and (opp_id, team_id) in matchup_results:
                mr = matchup_results[(opp_id, team_id)]
                home_win_pct = 1.0 - mr["away_win_pct"]
                weighted_win_sum += home_win_pct * n_home
                weighted_game_sum += n_home
                sim_rs_total += mr["avg_home_runs"] * n_home
                sim_ra_total += mr["avg_away_runs"] * n_home
                sim_games_total += n_home

        pred_win_pct = weighted_win_sum / weighted_game_sum if weighted_game_sum > 0 else 0.5
        pred_wins = round(pred_win_pct * total_games)

        pred_wins_list.append(pred_wins)
        actual_wins_list.append(actual_wins)

        # 실제 득실점 피타고라스 승률
        rs = team_rs.get(team_id, 1)
        ra = team_ra.get(team_id, 1)
        pythag_pct = rs ** PYTHAGOREAN_EXP / (rs ** PYTHAGOREAN_EXP + ra ** PYTHAGOREAN_EXP)
        pythag_wins = round(pythag_pct * total_games)
        pythag_wins_list.append(pythag_wins)

        # 시뮬레이션 득실점 피타고라스 승률
        if sim_games_total > 0:
            sim_rs = sim_rs_total / sim_games_total * total_games
            sim_ra = sim_ra_total / sim_games_total * total_games
        else:
            sim_rs = sim_ra = total_games * 4.5  # fallback

        sim_pythag_pct = sim_rs ** PYTHAGOREAN_EXP / (sim_rs ** PYTHAGOREAN_EXP + sim_ra ** PYTHAGOREAN_EXP)
        sim_pythag_wins = round(sim_pythag_pct * total_games)
        sim_pythag_wins_list.append(sim_pythag_wins)

        team_details.append({
            "team_id": team_id,
            "name": actual_info["name"],
            "pred_wins": pred_wins,
            "actual_wins": actual_wins,
            "pythag_wins": pythag_wins,
            "sim_pythag_wins": sim_pythag_wins,
            "diff": pred_wins - actual_wins,
        })

    pred_arr = np.array(pred_wins_list)
    actual_arr = np.array(actual_wins_list)
    pythag_arr = np.array(pythag_wins_list)
    sim_pythag_arr = np.array(sim_pythag_wins_list)

    wins_rmse = float(np.sqrt(np.mean((pred_arr - actual_arr) ** 2)))
    wins_corr = float(np.corrcoef(pred_arr, actual_arr)[0, 1]) if len(pred_arr) > 2 else 0.0
    pythag_rmse = float(np.sqrt(np.mean((pythag_arr - actual_arr) ** 2)))
    sim_pythag_rmse = float(np.sqrt(np.mean((sim_pythag_arr - actual_arr) ** 2)))
    sim_pythag_vs_direct = float(np.sqrt(np.mean((sim_pythag_arr - pred_arr) ** 2)))

    # 플레이오프 적중 (2024: 상위 12팀)
    actual_sorted = sorted(team_details, key=lambda x: x["actual_wins"], reverse=True)
    pred_sorted = sorted(team_details, key=lambda x: x["pred_wins"], reverse=True)
    actual_playoff = {t["team_id"] for t in actual_sorted[:12]}
    pred_playoff = {t["team_id"] for t in pred_sorted[:12]}
    playoff_correct = len(actual_playoff & pred_playoff)

    result = L4Result(
        n_teams=len(team_details),
        wins_rmse=wins_rmse,
        wins_corr=wins_corr,
        playoff_correct=playoff_correct,
        playoff_total=12,
        pythag_wins_rmse=pythag_rmse,
        sim_pythag_wins_rmse=sim_pythag_rmse,
        sim_pythag_vs_direct_rmse=sim_pythag_vs_direct,
        team_details=team_details,
    )

    logger.info(
        "L4: wins RMSE=%.1f (pythag=%.1f, sim_pythag=%.1f, sim_pythag_vs_direct=%.1f), corr=%.3f, playoff=%d/12",
        wins_rmse, pythag_rmse, sim_pythag_rmse, sim_pythag_vs_direct, wins_corr, playoff_correct,
    )

    return result
