"""1단계 검증: StatManager 비교 테스트."""

import logging
import time

import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

from data.pipeline import DugoutDataPipeline
from data.constants import TEAM_MAPPING
from engine.game import simulate_game
from engine.game_managed import simulate_managed_game
from engine.models import ParkFactors
from manager.stat_manager import StatManager
from manager.philosophy import NEUTRAL, ANALYTICS, OLD_SCHOOL, PRESETS


def run_comparison(
    away_team, home_team, park, league, n_games, seed,
    away_manager=None, home_manager=None, label="",
):
    """N경기 시뮬레이션하여 결과 요약."""
    rng = np.random.default_rng(seed)
    away_wins = 0
    total_runs = {"away": 0, "home": 0}
    total_decisions = 0
    total_ibbs = 0

    for _ in range(n_games):
        away_team.reset_bullpen()
        home_team.reset_bullpen()
        game_seed = int(rng.integers(1_000_000_000))

        if away_manager is not None or home_manager is not None:
            result, decisions = simulate_managed_game(
                away_team, home_team, park, league,
                np.random.default_rng(game_seed),
                away_manager=away_manager,
                home_manager=home_manager,
            )
            total_decisions += len(decisions)
            for d in decisions:
                if d.decision.action == "intentional_walk":
                    total_ibbs += 1
        else:
            result = simulate_game(
                away_team, home_team, park, league,
                np.random.default_rng(game_seed),
            )

        if result.winner == "away":
            away_wins += 1
        total_runs["away"] += result.score["away"]
        total_runs["home"] += result.score["home"]

    away_pct = away_wins / n_games
    avg_away = total_runs["away"] / n_games
    avg_home = total_runs["home"] / n_games

    return {
        "label": label,
        "n": n_games,
        "away_win_pct": away_pct,
        "avg_away_runs": avg_away,
        "avg_home_runs": avg_home,
        "total_decisions": total_decisions,
        "total_ibbs": total_ibbs,
    }


def main():
    pipeline = DugoutDataPipeline(season=2024)
    data = pipeline.load_all()

    # 두 팀 선택: NYY vs BOS
    away = data.teams["NYY"]
    home = data.teams["BOS"]
    park_name = TEAM_MAPPING["BOS"]["park"]
    park = data.parks.get(park_name)
    if park is None:
        park = ParkFactors(park_name=park_name, pf_1b=100, pf_2b=100, pf_3b=100, pf_hr=100)
    league = data.league

    N = 1000
    seed = 42

    print("=" * 65)
    print(" Phase 1-C Stage 1 Validation: StatManager Tests")
    print("=" * 65)
    print()

    # ── Test 1: Neutral vs Phase 0 ──
    print("── Test 1: StatManager(neutral) vs Phase 0 Auto Rules ──")
    t0 = time.time()

    # Phase 0
    r_phase0 = run_comparison(away, home, park, league, N, seed, label="Phase 0 (auto)")

    # Neutral manager (both sides)
    neutral = StatManager(NEUTRAL)
    r_neutral = run_comparison(
        away, home, park, league, N, seed,
        away_manager=StatManager(NEUTRAL),
        home_manager=StatManager(NEUTRAL),
        label="StatManager(neutral)",
    )

    elapsed = time.time() - t0
    print(f"  {r_phase0['label']:30s}  Win%: {r_phase0['away_win_pct']:.3f}  "
          f"Runs: {r_phase0['avg_away_runs']:.2f}-{r_phase0['avg_home_runs']:.2f}")
    print(f"  {r_neutral['label']:30s}  Win%: {r_neutral['away_win_pct']:.3f}  "
          f"Runs: {r_neutral['avg_away_runs']:.2f}-{r_neutral['avg_home_runs']:.2f}  "
          f"Decisions: {r_neutral['total_decisions']}")
    wp_diff = abs(r_phase0["away_win_pct"] - r_neutral["away_win_pct"])
    print(f"  Win% difference: {wp_diff:.3f}  ({'PASS' if wp_diff < 0.05 else 'WARN'}: < 0.05 expected)")
    print(f"  Time: {elapsed:.1f}s")
    print()

    # ── Test 2: Aggressive vs Conservative ──
    print("── Test 2: Analytics vs Old School (Philosophy Comparison) ──")
    t0 = time.time()

    r_analytics = run_comparison(
        away, home, park, league, N, seed,
        away_manager=StatManager(ANALYTICS),
        home_manager=StatManager(ANALYTICS),
        label="StatManager(analytics)",
    )
    r_oldschool = run_comparison(
        away, home, park, league, N, seed,
        away_manager=StatManager(OLD_SCHOOL),
        home_manager=StatManager(OLD_SCHOOL),
        label="StatManager(old_school)",
    )

    elapsed = time.time() - t0
    print(f"  {r_analytics['label']:30s}  Win%: {r_analytics['away_win_pct']:.3f}  "
          f"Runs: {r_analytics['avg_away_runs']:.2f}-{r_analytics['avg_home_runs']:.2f}  "
          f"Decisions: {r_analytics['total_decisions']}  IBBs: {r_analytics['total_ibbs']}")
    print(f"  {r_oldschool['label']:30s}  Win%: {r_oldschool['away_win_pct']:.3f}  "
          f"Runs: {r_oldschool['avg_away_runs']:.2f}-{r_oldschool['avg_home_runs']:.2f}  "
          f"Decisions: {r_oldschool['total_decisions']}  IBBs: {r_oldschool['total_ibbs']}")
    print(f"  Time: {elapsed:.1f}s")
    print()

    # ── Test 3: IBB Effect ──
    print("── Test 3: IBB Effect (old_school has IBB, neutral has none) ──")
    # old_school은 IBB 적극적, neutral은 IBB 안 함
    print(f"  Old school IBBs: {r_oldschool['total_ibbs']}")
    print(f"  Neutral IBBs:    {r_neutral['total_ibbs']}")
    print(f"  Analytics IBBs:  {r_analytics['total_ibbs']}")
    ibb_diff = r_oldschool["total_ibbs"] - r_neutral["total_ibbs"]
    print(f"  IBB difference (old_school - neutral): {ibb_diff}")
    print(f"  {'PASS' if ibb_diff > 0 else 'WARN'}: old_school should have more IBBs")
    print()

    # ── Summary ──
    print("── All Philosophies Summary ──")
    print(f"  {'Philosophy':20s}  {'Win%':>6s}  {'AwayR':>6s}  {'HomeR':>6s}  {'Decs':>5s}  {'IBBs':>5s}")
    for phil_name in ["neutral", "analytics", "old_school", "win_now", "development"]:
        phil = PRESETS.get(phil_name, NEUTRAL)
        r = run_comparison(
            away, home, park, league, N, seed,
            away_manager=StatManager(phil),
            home_manager=StatManager(phil),
            label=phil_name,
        )
        print(f"  {phil_name:20s}  {r['away_win_pct']:6.3f}  "
              f"{r['avg_away_runs']:6.2f}  {r['avg_home_runs']:6.2f}  "
              f"{r['total_decisions']:5d}  {r['total_ibbs']:5d}")

    print()
    print("Stage 1 validation complete.")


if __name__ == "__main__":
    main()
