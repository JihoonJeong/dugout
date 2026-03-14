"""L1: 타석 확률 모델 검증 — 개별 선수 성적 비교.

V0.1 재설계: 리그 평균 투수 대신, 각 타자가 실제 상대한 팀들의
가중 평균 투수를 사용하여 확률 산출. 이를 통해 Log5 항등원 성질을
우회하고 실질적인 모델 검증이 가능.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from engine.at_bat import calculate_matchup_probabilities
from engine.models import BatterStats, LeagueStats, ParkFactors, PitcherStats, Team
from .ground_truth import ActualResults

logger = logging.getLogger(__name__)

# wOBA 가중치 (2024 FanGraphs Guts!)
WOBA_WEIGHTS = {
    "BB": 0.690,
    "HBP": 0.722,
    "1B": 0.883,
    "2B": 1.244,
    "3B": 1.569,
    "HR": 2.004,
}


def predicted_woba(probs: dict[str, float]) -> float:
    """확률 분포에서 wOBA를 역산."""
    return sum(probs.get(event, 0) * weight for event, weight in WOBA_WEIGHTS.items())


@dataclass
class L1Result:
    n_batters: int
    k_rmse: float
    bb_rmse: float
    hr_rmse: float
    woba_rmse: float
    woba_corr: float
    league_avg_restoration: dict[str, float]  # event → |weighted_avg - league_rate|
    player_details: list[dict]  # 개별 선수 결과
    spot_checks: list[dict]  # 알려진 선수 스팟체크

    def passed(self) -> dict[str, bool]:
        return {
            "k_rmse": self.k_rmse < 0.040,
            "bb_rmse": self.bb_rmse < 0.030,
            "hr_rmse": self.hr_rmse < 0.015,
            "woba_rmse": self.woba_rmse < 0.030,
            "woba_corr": self.woba_corr > 0.80,
        }


def _build_team_avg_pitchers(
    teams: dict[str, Team],
    league: LeagueStats,
) -> dict[str, PitcherStats]:
    """팀별 가중 평균 투수 생성 (선발 + 불펜의 PA 가중 합산)."""
    team_pitchers: dict[str, PitcherStats] = {}

    for team_id, team in teams.items():
        pitchers = [team.starter] + team.bullpen
        total_pa = sum(p.pa_against for p in pitchers)
        if total_pa == 0:
            continue

        k_rate = sum(p.k_rate * p.pa_against for p in pitchers) / total_pa
        bb_rate = sum(p.bb_rate * p.pa_against for p in pitchers) / total_pa
        hbp_rate = sum(p.hbp_rate * p.pa_against for p in pitchers) / total_pa
        hr_rate_bip = sum(p.hr_rate_bip * p.pa_against for p in pitchers) / total_pa
        go_fo_ratio = sum(p.go_fo_ratio * p.pa_against for p in pitchers) / total_pa

        # 가장 흔한 투수 손잡이 (투수진 PA 가중)
        r_pa = sum(p.pa_against for p in pitchers if p.hand == "R")
        hand = "R" if r_pa >= total_pa / 2 else "L"

        team_pitchers[team_id] = PitcherStats(
            player_id=f"avg_{team_id}",
            name=f"{team_id} Avg Pitcher",
            hand=hand,
            pa_against=total_pa,
            k_rate=k_rate,
            bb_rate=bb_rate,
            hbp_rate=hbp_rate,
            hr_rate_bip=hr_rate_bip,
            go_fo_ratio=go_fo_ratio,
        )

    return team_pitchers


def _build_opponent_schedule(
    game_actuals: list[dict],
) -> dict[str, dict[str, int]]:
    """팀별 상대 팀 경기 수 집계. {team: {opponent: n_games}}."""
    schedule: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for g in game_actuals:
        schedule[g["away"]][g["home"]] += 1
        schedule[g["home"]][g["away"]] += 1
    return dict(schedule)


def _make_opponent_pitcher(
    batter_team: str,
    opponent_schedule: dict[str, dict[str, int]],
    team_avg_pitchers: dict[str, PitcherStats],
    league: LeagueStats,
) -> PitcherStats:
    """타자가 상대한 팀들의 가중 평균 투수 생성."""
    opponents = opponent_schedule.get(batter_team, {})
    if not opponents:
        # fallback: 리그 평균
        return PitcherStats(
            player_id="lg_avg", name="League Average", hand="R",
            pa_against=10000,
            k_rate=league.k_rate, bb_rate=league.bb_rate, hbp_rate=league.hbp_rate,
            hr_rate_bip=league.hr_rate_bip, go_fo_ratio=league.go_fo_ratio,
        )

    total_games = 0
    k_sum = bb_sum = hbp_sum = hr_bip_sum = gofo_sum = 0.0

    for opp_id, n_games in opponents.items():
        opp_pitcher = team_avg_pitchers.get(opp_id)
        if opp_pitcher is None:
            continue
        total_games += n_games
        k_sum += opp_pitcher.k_rate * n_games
        bb_sum += opp_pitcher.bb_rate * n_games
        hbp_sum += opp_pitcher.hbp_rate * n_games
        hr_bip_sum += opp_pitcher.hr_rate_bip * n_games
        gofo_sum += opp_pitcher.go_fo_ratio * n_games

    if total_games == 0:
        return PitcherStats(
            player_id="lg_avg", name="League Average", hand="R",
            pa_against=10000,
            k_rate=league.k_rate, bb_rate=league.bb_rate, hbp_rate=league.hbp_rate,
            hr_rate_bip=league.hr_rate_bip, go_fo_ratio=league.go_fo_ratio,
        )

    return PitcherStats(
        player_id=f"opp_{batter_team}",
        name=f"Opponents of {batter_team}",
        hand="R",
        pa_against=10000,
        k_rate=k_sum / total_games,
        bb_rate=bb_sum / total_games,
        hbp_rate=hbp_sum / total_games,
        hr_rate_bip=hr_bip_sum / total_games,
        go_fo_ratio=gofo_sum / total_games,
    )


def run_l1(
    all_batters: dict[str, BatterStats],
    league: LeagueStats,
    actual: ActualResults,
    teams: dict[str, Team] | None = None,
    min_pa: int = 200,
) -> L1Result:
    """L1 검증 실행.

    teams가 주어지면 상대팀 가중 평균 투수를 사용 (실질적 검증).
    teams가 None이면 리그 평균 투수 사용 (파이프라인 무결성 테스트).
    """
    neutral_park = ParkFactors(park_name="Neutral", pf_1b=100, pf_2b=100, pf_3b=100, pf_hr=100)

    # 상대 투수 결정
    if teams is not None and actual.game_actuals:
        team_avg_pitchers = _build_team_avg_pitchers(teams, league)
        opponent_schedule = _build_opponent_schedule(actual.game_actuals)

        # 타자 team 매핑 (batter_actuals에서 추출)
        batter_teams: dict[str, str] = {}
        for pid, act_info in actual.batter_actuals.items():
            team = act_info.get("team", "")
            # 멀티팀 선수 처리: "- - -" 또는 빈 팀은 제외
            if team and team != "- - -":
                batter_teams[pid] = team

        # 팀별 상대 투수 캐시
        _opp_pitcher_cache: dict[str, PitcherStats] = {}
        use_opponent = True
        logger.info("L1: using opponent-weighted pitchers (%d teams)", len(team_avg_pitchers))
    else:
        use_opponent = False
        avg_pitcher = PitcherStats(
            player_id="lg_avg", name="League Average", hand="R",
            pa_against=10000,
            k_rate=league.k_rate, bb_rate=league.bb_rate, hbp_rate=league.hbp_rate,
            hr_rate_bip=league.hr_rate_bip, go_fo_ratio=league.go_fo_ratio,
        )
        logger.info("L1: using league-average pitcher (integrity test mode)")

    pred_k, actual_k = [], []
    pred_bb, actual_bb = [], []
    pred_hr, actual_hr = [], []
    pred_woba_list, actual_woba_list = [], []
    player_details = []

    # PA 가중 평균용
    total_pa = 0
    weighted_probs = {e: 0.0 for e in ["K", "BB", "HBP", "1B", "2B", "3B", "HR", "GO", "FO"]}

    for pid, batter in all_batters.items():
        act = actual.batter_actuals.get(pid)
        if act is None or act["pa"] < min_pa:
            continue
        if act.get("woba") is None:
            continue

        # 상대 투수 결정
        if use_opponent:
            batter_team = batter_teams.get(pid)
            if batter_team is None:
                continue  # 팀 불명 → 스킵
            if batter_team not in _opp_pitcher_cache:
                _opp_pitcher_cache[batter_team] = _make_opponent_pitcher(
                    batter_team, opponent_schedule, team_avg_pitchers, league,
                )
            pitcher = _opp_pitcher_cache[batter_team]
        else:
            pitcher = avg_pitcher

        probs = calculate_matchup_probabilities(batter, pitcher, league, neutral_park)
        p_woba = predicted_woba(probs)

        pred_k.append(probs["K"])
        actual_k.append(act["k_rate"])
        pred_bb.append(probs["BB"])
        actual_bb.append(act["bb_rate"])
        pred_hr.append(probs["HR"])
        actual_hr.append(act["hr_rate"])
        pred_woba_list.append(p_woba)
        actual_woba_list.append(act["woba"])

        # PA 가중평균
        pa = act["pa"]
        total_pa += pa
        for e in weighted_probs:
            weighted_probs[e] += pa * probs[e]

        player_details.append({
            "player_id": pid,
            "name": batter.name,
            "pa": pa,
            "pred_k": probs["K"],
            "actual_k": act["k_rate"],
            "pred_bb": probs["BB"],
            "actual_bb": act["bb_rate"],
            "actual_bb_no_ibb": act.get("bb_rate_no_ibb", act["bb_rate"]),
            "pred_hr": probs["HR"],
            "actual_hr": act["hr_rate"],
            "pred_woba": p_woba,
            "actual_woba": act["woba"],
            "woba_error": p_woba - act["woba"],
        })

    pred_k = np.array(pred_k)
    actual_k = np.array(actual_k)
    pred_bb = np.array(pred_bb)
    actual_bb = np.array(actual_bb)
    pred_hr = np.array(pred_hr)
    actual_hr = np.array(actual_hr)
    pred_woba_arr = np.array(pred_woba_list)
    actual_woba_arr = np.array(actual_woba_list)

    k_rmse = float(np.sqrt(np.mean((pred_k - actual_k) ** 2)))
    bb_rmse = float(np.sqrt(np.mean((pred_bb - actual_bb) ** 2)))
    hr_rmse = float(np.sqrt(np.mean((pred_hr - actual_hr) ** 2)))
    woba_rmse = float(np.sqrt(np.mean((pred_woba_arr - actual_woba_arr) ** 2)))
    woba_corr = float(np.corrcoef(pred_woba_arr, actual_woba_arr)[0, 1]) if len(pred_woba_arr) > 2 else 0.0

    # 리그 평균 복원
    league_rates = {
        "K": league.k_rate, "BB": league.bb_rate, "HBP": league.hbp_rate,
    }
    league_avg_restoration = {}
    if total_pa > 0:
        for e, lg_rate in league_rates.items():
            weighted_avg = weighted_probs[e] / total_pa
            league_avg_restoration[e] = abs(weighted_avg - lg_rate)

    # 스팟체크: wOBA 괴리 상위 10
    spot_checks = sorted(player_details, key=lambda x: abs(x["woba_error"]), reverse=True)[:10]

    result = L1Result(
        n_batters=len(pred_k),
        k_rmse=k_rmse,
        bb_rmse=bb_rmse,
        hr_rmse=hr_rmse,
        woba_rmse=woba_rmse,
        woba_corr=woba_corr,
        league_avg_restoration=league_avg_restoration,
        player_details=player_details,
        spot_checks=spot_checks,
    )

    logger.info(
        "L1: n=%d, K%% RMSE=%.3f, BB%% RMSE=%.3f, HR RMSE=%.3f, wOBA RMSE=%.3f, wOBA corr=%.3f",
        result.n_batters, k_rmse, bb_rmse, hr_rmse, woba_rmse, woba_corr,
    )

    return result
