"""시즌 엔진 — 하루/경기 단위 진행."""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict

import numpy as np

from data.constants import TEAM_MAPPING
from data.pipeline import DugoutData
from data.schedule import GameRecord, fetch_season_schedule
from engine.game import simulate_game
from engine.models import ParkFactors
from manager.stat_manager import StatManager
from manager.philosophy import NEUTRAL

from .auto_manager import AutoTeamManager
from .highlights import extract_highlights
from .state import GameResultSummary, ScheduledGame, SeasonState, TeamRecord

logger = logging.getLogger(__name__)


def create_season(
    data: DugoutData,
    user_team_id: str,
    philosophy: str = "analytics",
    season: int = 2025,
    cache_dir: str = "cache/",
) -> SeasonState:
    """시즌 초기화."""
    schedule_records = fetch_season_schedule(season, cache_dir=cache_dir)

    # 날짜별 경기 그룹화
    schedule_by_date: dict[str, list[ScheduledGame]] = defaultdict(list)
    for g in schedule_records:
        sg = ScheduledGame(
            game_date=g.date,
            away_team_id=g.away_team_id,
            home_team_id=g.home_team_id,
            away_starter_name=g.away_starter_name,
            home_starter_name=g.home_starter_name,
        )
        schedule_by_date[g.date].append(sg)

    # 팀 성적 초기화
    records = {}
    for team_id in data.teams:
        records[team_id] = TeamRecord(team_id=team_id)

    dates = sorted(schedule_by_date.keys())
    first_date = dates[0] if dates else "2025-03-27"

    state = SeasonState(
        season_id=str(uuid.uuid4())[:8],
        season=season,
        user_team_id=user_team_id,
        philosophy=philosophy,
        current_date=first_date,
        schedule=dict(schedule_by_date),
        records=records,
    )

    logger.info(
        "Season created: %s, team=%s, %d dates, %d total games",
        state.season_id, user_team_id, len(dates),
        sum(len(gs) for gs in schedule_by_date.values()),
    )

    return state


def advance_day(
    state: SeasonState,
    data: DugoutData,
    auto_mgr: AutoTeamManager,
    rng: np.random.Generator,
    game_mode: str = "sim",
) -> list[GameResultSummary]:
    """현재 날짜의 모든 경기를 진행하고 다음 날로 이동."""
    date = state.current_date
    games = state.get_games_on_date(date)

    if not games:
        _advance_to_next_date(state)
        return []

    results = []
    for game in games:
        if game.result is not None:
            continue  # 이미 진행된 경기

        # 유저 팀 경기인 경우 game_mode 적용
        is_user_game = (
            game.away_team_id == state.user_team_id
            or game.home_team_id == state.user_team_id
        )

        if is_user_game and game_mode in ("gameday", "live"):
            game.game_mode = game_mode
            # gameday/live는 별도 처리 — 여기서는 스킵
            continue

        # Sim 모드: 즉시 시뮬레이션
        result = simulate_auto_game(game, data, auto_mgr, rng)
        game.result = result
        update_standings(state, game)
        results.append(result)

    _advance_to_next_date(state)
    return results


def simulate_auto_game(
    game: ScheduledGame,
    data: DugoutData,
    auto_mgr: AutoTeamManager,
    rng: np.random.Generator,
) -> GameResultSummary:
    """단일 경기 자동 시뮬레이션 (n_sims=1)."""
    away_team = auto_mgr.get_team_for_game(game.away_team_id)
    home_team = auto_mgr.get_team_for_game(game.home_team_id)

    park_name = TEAM_MAPPING[game.home_team_id]["park"]
    park = data.parks.get(park_name)
    if park is None:
        park = ParkFactors(park_name=park_name, pf_1b=100, pf_2b=100, pf_3b=100, pf_hr=100)

    away_team.reset_bullpen()
    home_team.reset_bullpen()

    game_seed = int(rng.integers(1_000_000_000))
    result = simulate_game(away_team, home_team, park, data.league,
                           np.random.default_rng(game_seed))

    highlights = extract_highlights(result, game.away_team_id, game.home_team_id)

    return GameResultSummary(
        away_score=result.score["away"],
        home_score=result.score["home"],
        winner=result.winner,
        innings=result.innings_played,
        away_hits=result.hits["away"],
        home_hits=result.hits["home"],
        highlights=highlights,
    )


def update_standings(state: SeasonState, game: ScheduledGame) -> None:
    """경기 결과를 순위표에 반영."""
    r = game.result
    if r is None:
        return

    away_rec = state.records[game.away_team_id]
    home_rec = state.records[game.home_team_id]

    away_rec.runs_scored += r.away_score
    away_rec.runs_allowed += r.home_score
    home_rec.runs_scored += r.home_score
    home_rec.runs_allowed += r.away_score

    if r.winner == "away":
        away_rec.wins += 1
        home_rec.losses += 1
    elif r.winner == "home":
        home_rec.wins += 1
        away_rec.losses += 1
    else:
        # 무승부 (극히 드물지만)
        pass


def sim_multiple_days(
    state: SeasonState,
    data: DugoutData,
    auto_mgr: AutoTeamManager,
    rng: np.random.Generator,
    n_days: int = 7,
) -> int:
    """여러 날 한 번에 시뮬레이션. 반환: 진행된 경기 수."""
    total_games = 0
    for _ in range(n_days):
        if state.is_complete:
            break
        results = advance_day(state, data, auto_mgr, rng)
        total_games += len(results)
    return total_games


def _advance_to_next_date(state: SeasonState) -> None:
    """다음 경기가 있는 날짜로 이동."""
    dates = sorted(state.schedule.keys())
    current_idx = None
    for i, d in enumerate(dates):
        if d == state.current_date:
            current_idx = i
            break

    if current_idx is None or current_idx + 1 >= len(dates):
        state.is_complete = True
        return

    state.current_date = dates[current_idx + 1]
    state.day_index += 1
