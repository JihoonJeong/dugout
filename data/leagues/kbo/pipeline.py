"""KBO DugoutData 빌더 — extract → transform → team build → DugoutData."""

from __future__ import annotations

import logging
import pickle
from pathlib import Path

from engine.models import BatterStats, ParkFactors, PitcherStats, Team
from data.pipeline import DugoutData

from .extract import fetch_batting_stats, fetch_pitching_stats
from .parks import PARK_FACTORS
from .teams import TEAM_MAPPING
from .transform import calculate_kbo_league_stats, convert_batter, convert_pitcher

logger = logging.getLogger(__name__)


def build_kbo_data(
    season: int = 2025,
    cache_dir: str = "cache/",
    force_refresh: bool = False,
) -> DugoutData:
    """KBO 시즌 데이터를 로드하여 DugoutData로 반환."""
    engine_cache = Path(cache_dir) / "engine" / f"kbo_data_{season}.pkl"

    if not force_refresh and engine_cache.exists():
        logger.info("Loading cached KBO engine data: %s", engine_cache)
        with open(engine_cache, "rb") as f:
            return pickle.load(f)

    raw_dir = str(Path(cache_dir) / "raw")

    # 1. Extract
    batters_raw = fetch_batting_stats(season, cache_dir=raw_dir)
    pitchers_raw = fetch_pitching_stats(season, cache_dir=raw_dir)

    # 2. League stats
    league = calculate_kbo_league_stats(batters_raw, season)
    logger.info(
        "KBO league stats: K%%=%.3f, BB%%=%.3f, HR/BIP=%.3f",
        league.k_rate, league.bb_rate, league.hr_rate_bip,
    )

    # 3. Convert to engine format
    all_batters: dict[str, BatterStats] = {}
    batter_teams: dict[str, str] = {}
    for raw in batters_raw:
        bs = convert_batter(raw, league)
        if bs:
            all_batters[bs.player_id] = bs
            batter_teams[bs.player_id] = raw.team_id

    all_pitchers: dict[str, PitcherStats] = {}
    pitcher_teams: dict[str, str] = {}
    pitcher_roles: dict[str, str] = {}
    pitcher_ips: dict[str, float] = {}
    for raw in pitchers_raw:
        result = convert_pitcher(raw, league)
        if result:
            ps, role = result
            all_pitchers[ps.player_id] = ps
            pitcher_teams[ps.player_id] = raw.team_id
            pitcher_roles[ps.player_id] = role
            pitcher_ips[ps.player_id] = raw.ip

    logger.info("KBO: %d batters, %d pitchers converted", len(all_batters), len(all_pitchers))

    # 4. Park factors
    parks: dict[str, ParkFactors] = {}
    for park_name, pf in PARK_FACTORS.items():
        parks[park_name] = ParkFactors(
            park_name=park_name,
            pf_1b=pf["1B"], pf_2b=pf["2B"], pf_3b=pf["3B"], pf_hr=pf["HR"],
        )

    # 5. Build teams
    teams: dict[str, Team] = {}
    for team_id, team_info in TEAM_MAPPING.items():
        team_batters = {
            pid: all_batters[pid]
            for pid, t in batter_teams.items()
            if t == team_id and pid in all_batters
        }
        team_pitchers_dict = {
            pid: all_pitchers[pid]
            for pid, t in pitcher_teams.items()
            if t == team_id and pid in all_pitchers
        }

        if not team_batters or not team_pitchers_dict:
            logger.warning("KBO team %s has no data, skipping", team_id)
            continue

        # Lineup: top 9 by PA
        lineup = sorted(team_batters.values(), key=lambda b: b.pa, reverse=True)[:9]

        # Starter: SP with most IP
        starters = [p for pid, p in team_pitchers_dict.items() if pitcher_roles.get(pid) == "SP"]
        relievers = [p for pid, p in team_pitchers_dict.items() if pitcher_roles.get(pid) == "RP"]

        if starters:
            starter = max(starters, key=lambda p: pitcher_ips.get(p.player_id, 0))
        else:
            starter = max(team_pitchers_dict.values(), key=lambda p: pitcher_ips.get(p.player_id, 0))

        # Bullpen: top 5 RP by IP (excluding starter)
        bullpen_candidates = [p for p in relievers if p.player_id != starter.player_id]
        if len(bullpen_candidates) < 4:
            extra = [p for p in starters if p.player_id != starter.player_id]
            bullpen_candidates.extend(extra)
        bullpen = sorted(bullpen_candidates, key=lambda p: pitcher_ips.get(p.player_id, 0), reverse=True)[:5]

        teams[team_id] = Team(
            team_id=team_id,
            name=team_info["name"],
            lineup=lineup,
            starter=starter,
            bullpen=bullpen,
        )

    logger.info("KBO: %d teams built", len(teams))

    data = DugoutData(
        season=season,
        all_batters=all_batters,
        all_pitchers=all_pitchers,
        league=league,
        parks=parks,
        teams=teams,
    )

    # Cache
    engine_cache.parent.mkdir(parents=True, exist_ok=True)
    with open(engine_cache, "wb") as f:
        pickle.dump(data, f)
    logger.info("Cached KBO engine data to %s", engine_cache)

    return data
