"""선발투수 임팩트 분석."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from io import StringIO

import numpy as np

from simulation.results import GameLevelResults

logger = logging.getLogger(__name__)


@dataclass
class StarterImpactReport:
    n_games: int
    mean_win_pct_spread: float  # 같은 팀의 선발별 승률 표준편차 평균
    team_spreads: dict[str, float]  # 팀별 선발 승률 표준편차
    top_starters: list[dict]  # 가장 높은 승률을 가진 선발
    bottom_starters: list[dict]  # 가장 낮은 승률을 가진 선발
    fallback_stats: dict[str, int]
    fallback_rate: float


def analyze_starter_impact(results: GameLevelResults) -> StarterImpactReport:
    """선발투수 교체가 경기 승률에 미치는 영향 분석."""

    # 팀별 선발별 승률 수집
    team_starter_wins: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for g in results.games:
        if g.sim_away_win_pct is None:
            continue
        # 어웨이 팀
        away_key = g.away_starter_name or "unknown"
        team_starter_wins[g.away_team_id][away_key].append(g.sim_away_win_pct)
        # 홈 팀
        home_key = g.home_starter_name or "unknown"
        team_starter_wins[g.home_team_id][home_key].append(1.0 - g.sim_away_win_pct)

    # 팀별 선발 승률 분산
    team_spreads: dict[str, float] = {}
    all_starter_entries = []

    for team_id, starters in team_starter_wins.items():
        starter_means = []
        for starter_name, win_pcts in starters.items():
            mean_wp = float(np.mean(win_pcts))
            starter_means.append(mean_wp)
            all_starter_entries.append({
                "team": team_id,
                "starter": starter_name,
                "games": len(win_pcts),
                "mean_win_pct": mean_wp,
            })

        if len(starter_means) > 1:
            team_spreads[team_id] = float(np.std(starter_means))
        else:
            team_spreads[team_id] = 0.0

    mean_spread = float(np.mean(list(team_spreads.values()))) if team_spreads else 0.0

    # 최고/최저 선발 (최소 5경기)
    qualified = [e for e in all_starter_entries if e["games"] >= 5]
    top = sorted(qualified, key=lambda x: x["mean_win_pct"], reverse=True)[:10]
    bottom = sorted(qualified, key=lambda x: x["mean_win_pct"])[:10]

    return StarterImpactReport(
        n_games=results.n_valid,
        mean_win_pct_spread=mean_spread,
        team_spreads=team_spreads,
        top_starters=top,
        bottom_starters=bottom,
        fallback_stats=results.fallback_stats,
        fallback_rate=results.fallback_rate,
    )


def format_starter_impact(report: StarterImpactReport) -> str:
    """임팩트 리포트 텍스트 생성."""
    buf = StringIO()
    w = buf.write

    w(f"{'=' * 60}\n")
    w(f" Starter Impact Analysis — {report.n_games} games\n")
    w(f"{'=' * 60}\n\n")

    w(f"  Mean win% spread across starters: {report.mean_win_pct_spread:.4f}\n")
    w(f"  Fallback rate: {report.fallback_rate:.1%}\n")
    w(f"  Fallback breakdown: {report.fallback_stats}\n\n")

    w("  Team starter spreads (std of starter avg win%):\n")
    sorted_teams = sorted(report.team_spreads.items(), key=lambda x: x[1], reverse=True)
    for team, spread in sorted_teams[:10]:
        w(f"    {team}: {spread:.4f}\n")
    w("\n")

    w("  Top starters by mean win% (min 5 games):\n")
    for s in report.top_starters[:5]:
        w(f"    {s['starter']:25s} ({s['team']})  {s['mean_win_pct']:.3f}  ({s['games']} G)\n")
    w("\n  Bottom starters:\n")
    for s in report.bottom_starters[:5]:
        w(f"    {s['starter']:25s} ({s['team']})  {s['mean_win_pct']:.3f}  ({s['games']} G)\n")

    return buf.getvalue()
