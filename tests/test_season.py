"""1단계 검증: 162경기 Sim 완주 + 순위표 정합성."""

import logging
import time

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

from data.pipeline import DugoutDataPipeline
from season.engine import create_season, sim_multiple_days
from season.auto_manager import AutoTeamManager


def main():
    pipeline = DugoutDataPipeline(season=2025)
    data = pipeline.load_all()

    user_team = "NYY"
    state = create_season(data, user_team_id=user_team, season=2025)
    auto_mgr = AutoTeamManager(data, user_team)
    rng = np.random.default_rng(42)

    print("=" * 60)
    print(" Phase 2 Stage 1: Full Season Simulation Test")
    print("=" * 60)
    print()
    print(f"  User team: {user_team}")
    print(f"  Total schedule dates: {len(state.schedule)}")
    total_scheduled = sum(len(gs) for gs in state.schedule.values())
    print(f"  Total scheduled games: {total_scheduled}")
    print()

    t0 = time.time()

    # 전체 시즌 시뮬레이션 (충분히 큰 n_days)
    total_games = sim_multiple_days(state, data, auto_mgr, rng, n_days=250)

    elapsed = time.time() - t0
    games_per_sec = total_games / elapsed if elapsed > 0 else 0

    print(f"  Simulated {total_games} games in {elapsed:.1f}s ({games_per_sec:.1f} games/s)")
    print(f"  Season complete: {state.is_complete}")
    print()

    # 순위표 정합성 검증
    print("── Standings Validation ──")
    total_wins = sum(r.wins for r in state.records.values())
    total_losses = sum(r.losses for r in state.records.values())
    print(f"  Total wins: {total_wins}")
    print(f"  Total losses: {total_losses}")
    print(f"  Wins == Losses: {total_wins == total_losses} ({'PASS' if total_wins == total_losses else 'FAIL'})")
    print(f"  Total games (wins+losses)/2: {(total_wins + total_losses) // 2}")
    print()

    # 각 팀 경기 수 확인
    game_counts = {}
    for team_id, rec in state.records.items():
        game_counts[team_id] = rec.games

    min_games = min(game_counts.values())
    max_games = max(game_counts.values())
    print(f"  Min games per team: {min_games}")
    print(f"  Max games per team: {max_games}")

    # 경기 수가 크게 벗어나는 팀 체크
    out_of_range = {t: g for t, g in game_counts.items() if g < 155 or g > 170}
    if out_of_range:
        print(f"  WARNING: Teams with unusual game counts: {out_of_range}")
    else:
        print(f"  All teams in 155-170 game range: PASS")
    print()

    # 유저 팀 성적
    ur = state.user_record
    print(f"── {user_team} Season Summary ──")
    print(f"  Record: {ur.wins}-{ur.losses} ({ur.win_pct:.3f})")
    print(f"  RS: {ur.runs_scored}, RA: {ur.runs_allowed}, Diff: {ur.run_diff:+d}")
    print()

    # 전체 순위표
    standings = state.get_standings()
    print("── Final Standings ──")
    print(f"  {'#':>3s}  {'Team':>5s}  {'W':>4s}  {'L':>4s}  {'Pct':>5s}  {'RS':>5s}  {'RA':>5s}  {'Diff':>5s}")
    for i, r in enumerate(standings):
        marker = " *" if r.team_id == user_team else ""
        print(f"  {i+1:3d}  {r.team_id:>5s}  {r.wins:4d}  {r.losses:4d}  "
              f"{r.win_pct:5.3f}  {r.runs_scored:5d}  {r.runs_allowed:5d}  {r.run_diff:+5d}{marker}")
    print()

    # 속도 체크
    target_speed = 5.0  # games/s minimum
    print(f"── Performance ──")
    print(f"  Target: > {target_speed} games/s")
    print(f"  Actual: {games_per_sec:.1f} games/s")
    print(f"  {'PASS' if games_per_sec >= target_speed else 'WARN'}")
    print()

    print("Stage 1 validation complete.")


if __name__ == "__main__":
    main()
