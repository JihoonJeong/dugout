"""경기별 선발투수 반영 시뮬레이션."""

from __future__ import annotations

import logging
import time
from collections import defaultdict

import numpy as np

from data.constants import TEAM_MAPPING
from data.extract import fetch_id_mapping
from data.game_team_builder import build_game_team, build_mlb_to_fg_map, resolve_starter
from data.pipeline import DugoutData
from data.schedule import GameRecord, fetch_season_schedule
from engine.monte_carlo import simulate_series
from .results import GameLevelResults

logger = logging.getLogger(__name__)


def run_game_level_simulation(
    data: DugoutData,
    season: int = 2024,
    n_sims: int = 1000,
    seed: int = 42,
    cache_dir: str = "cache/",
) -> GameLevelResults:
    """2024 전 경기에 대해 경기별 선발투수를 반영한 시뮬레이션 실행."""

    rng = np.random.default_rng(seed)

    # 1. 일정 데이터
    schedule = fetch_season_schedule(season, cache_dir=cache_dir)
    logger.info("Schedule: %d games", len(schedule))

    # 2. ID 매핑
    id_mapping = fetch_id_mapping(cache_dir=cache_dir)
    mlb_to_fg = build_mlb_to_fg_map(data, id_mapping)
    logger.info("MLB→FG pitcher mapping: %d entries", len(mlb_to_fg))

    # 3. 경기별 시뮬레이션
    results: list[GameRecord] = []
    fallback_count: dict[str, int] = defaultdict(int)
    n_skipped = 0

    t0 = time.time()
    for i, game in enumerate(schedule):
        if game.away_team_id not in data.teams or game.home_team_id not in data.teams:
            n_skipped += 1
            continue

        # 선발투수 해결
        away_starter, fb_a = resolve_starter(
            game.away_starter_mlb_id, game.away_starter_name,
            game.away_team_id, data, mlb_to_fg,
        )
        home_starter, fb_h = resolve_starter(
            game.home_starter_mlb_id, game.home_starter_name,
            game.home_team_id, data, mlb_to_fg,
        )

        if fb_a:
            fallback_count[fb_a] += 1
            game.away_starter_fallback = fb_a
        if fb_h:
            fallback_count[fb_h] += 1
            game.home_starter_fallback = fb_h

        # 팀 구성
        away_team = build_game_team(game.away_team_id, away_starter, data)
        home_team = build_game_team(game.home_team_id, home_starter, data)

        park_name = TEAM_MAPPING[game.home_team_id]["park"]
        park = data.parks.get(park_name)
        if park is None:
            from engine.models import ParkFactors
            park = ParkFactors(park_name=park_name, pf_1b=100, pf_2b=100, pf_3b=100, pf_hr=100)

        # 시뮬레이션
        game_seed = int(rng.integers(1_000_000_000))
        series = simulate_series(away_team, home_team, park, data.league,
                                 n_simulations=n_sims, seed=game_seed)

        game.sim_away_win_pct = series.away_win_pct
        game.sim_avg_away_runs = series.avg_away_runs
        game.sim_avg_home_runs = series.avg_home_runs
        results.append(game)

        if (i + 1) % 500 == 0:
            elapsed = time.time() - t0
            logger.info("  %d/%d games simulated (%.1fs)", i + 1, len(schedule), elapsed)

    elapsed = time.time() - t0
    logger.info(
        "Game-level simulation complete: %d games in %.1fs (%.1f games/s)",
        len(results), elapsed, len(results) / elapsed if elapsed > 0 else 0,
    )
    logger.info("Fallback stats: %s", dict(fallback_count))
    logger.info("Skipped: %d games", n_skipped)

    return GameLevelResults(
        games=results,
        fallback_stats=dict(fallback_count),
        n_sims_per_game=n_sims,
        n_skipped=n_skipped,
    )
