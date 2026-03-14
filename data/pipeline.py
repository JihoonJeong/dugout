"""Dugout 데이터 파이프라인 — 메인 인터페이스."""

from __future__ import annotations

import logging
import os
import pickle
from dataclasses import dataclass
from pathlib import Path

from engine.models import BatterStats, LeagueStats, ParkFactors, PitcherStats, Team
from .constants import TEAM_MAPPING
from .extract import fetch_batting_stats, fetch_id_mapping, fetch_pitching_stats, fetch_player_hands, fetch_statcast_splits
from .park_factors import extract_park_factors
from .team_builder import build_team
from .transform import (
    calculate_league_stats,
    prepare_splits_lookup,
    to_batter_stats,
    to_pitcher_stats,
    transform_batters,
    transform_pitchers,
)

logger = logging.getLogger(__name__)


@dataclass
class DugoutData:
    season: int
    all_batters: dict[str, BatterStats]
    all_pitchers: dict[str, PitcherStats]
    league: LeagueStats
    parks: dict[str, ParkFactors]
    teams: dict[str, Team]

    def get_matchup(self, away_id: str, home_id: str) -> tuple[Team, Team, ParkFactors]:
        """경기 시뮬레이션을 위한 매치업 데이터 추출."""
        away = self.teams[away_id]
        home = self.teams[home_id]
        park_name = TEAM_MAPPING[home_id]["park"]
        park = self.parks[park_name]
        return away, home, park


class DugoutDataPipeline:
    """Dugout 엔진에 데이터를 공급하는 메인 파이프라인."""

    def __init__(self, cache_dir: str = "cache/", season: int = 2024):
        self.cache_dir = cache_dir
        self.season = season

    def load_all(self, force_refresh: bool = False) -> DugoutData:
        """전체 데이터를 로드하여 엔진에 공급 가능한 형태로 반환."""

        # 엔진 캐시 확인
        engine_cache = Path(self.cache_dir) / "engine" / f"dugout_data_{self.season}.pkl"
        if not force_refresh and engine_cache.exists():
            logger.info("Loading cached engine data: %s", engine_cache)
            with open(engine_cache, "rb") as f:
                return pickle.load(f)

        # 1. Raw 데이터 추출
        raw_batting = fetch_batting_stats(self.season, self.cache_dir, force=force_refresh)
        raw_pitching = fetch_pitching_stats(self.season, self.cache_dir, force=force_refresh)
        player_hands = fetch_player_hands(self.season, self.cache_dir, force=force_refresh)
        id_mapping = fetch_id_mapping(self.cache_dir, force=force_refresh)

        # 2. Intermediate 변환
        batters_int = transform_batters(raw_batting, id_mapping, player_hands, self.season)
        pitchers_int = transform_pitchers(raw_pitching, id_mapping, player_hands, self.season)

        # 2.5. Statcast platoon splits
        splits_df = fetch_statcast_splits(self.season, self.cache_dir, force=force_refresh)
        splits_lookup = prepare_splits_lookup(splits_df)
        logger.info("Splits lookup: %d entries", len(splits_lookup))

        # 3. 리그 평균 산출
        league = calculate_league_stats(batters_int, self.season)
        logger.info(
            "League stats: K%%=%.3f, BB%%=%.3f, HR/BIP=%.3f, GO/FO=%.2f",
            league.k_rate, league.bb_rate, league.hr_rate_bip, league.go_fo_ratio,
        )

        # 4. Engine-ready 변환
        all_batters = {}
        for bi in batters_int:
            try:
                all_batters[bi.player_id] = to_batter_stats(bi, league, splits_data=splits_lookup)
            except Exception as e:
                logger.warning("Failed to convert batter %s: %s", bi.name, e)

        all_pitchers = {}
        for pi in pitchers_int:
            try:
                all_pitchers[pi.player_id] = to_pitcher_stats(pi, league, splits_data=splits_lookup)
            except Exception as e:
                logger.warning("Failed to convert pitcher %s: %s", pi.name, e)

        # 투수 역할/이닝 매핑
        pitcher_roles = {pi.player_id: pi.role for pi in pitchers_int}
        pitcher_ips = {pi.player_id: pi.ip for pi in pitchers_int}
        # 타자/투수 팀 매핑
        batter_teams = {bi.player_id: bi.team for bi in batters_int}
        pitcher_teams = {pi.player_id: pi.team for pi in pitchers_int}

        # 5. Park factors
        parks = extract_park_factors(self.season)

        # 6. 팀 구성
        teams = {}
        for team_id in TEAM_MAPPING:
            team_batters = {
                pid: all_batters[pid]
                for pid, team in batter_teams.items()
                if team == team_id and pid in all_batters
            }
            team_pitchers = {
                pid: all_pitchers[pid]
                for pid, team in pitcher_teams.items()
                if team == team_id and pid in all_pitchers
            }
            team_pitcher_roles = {pid: pitcher_roles[pid] for pid in team_pitchers if pid in pitcher_roles}
            team_pitcher_ips = {pid: pitcher_ips[pid] for pid in team_pitchers if pid in pitcher_ips}

            team = build_team(team_id, team_batters, team_pitchers, team_pitcher_roles, team_pitcher_ips)
            if team is not None:
                teams[team_id] = team

        logger.info("Built %d teams", len(teams))

        # 7. 검증
        self._validate(all_batters, all_pitchers, league, parks, teams)

        data = DugoutData(
            season=self.season,
            all_batters=all_batters,
            all_pitchers=all_pitchers,
            league=league,
            parks=parks,
            teams=teams,
        )

        # 캐시 저장
        engine_cache.parent.mkdir(parents=True, exist_ok=True)
        with open(engine_cache, "wb") as f:
            pickle.dump(data, f)
        logger.info("Cached engine data to %s", engine_cache)

        return data

    def _validate(
        self,
        all_batters: dict[str, BatterStats],
        all_pitchers: dict[str, PitcherStats],
        league: LeagueStats,
        parks: dict[str, ParkFactors],
        teams: dict[str, Team],
    ) -> None:
        """데이터 무결성 검증."""
        issues = []

        # 선수 수
        if len(all_batters) < 500:
            issues.append(f"Too few batters: {len(all_batters)} (expected ≥500)")
        if len(all_pitchers) < 400:
            issues.append(f"Too few pitchers: {len(all_pitchers)} (expected ≥400)")

        # 리그 평균 범위
        if not (0.18 <= league.k_rate <= 0.28):
            issues.append(f"League K% out of range: {league.k_rate:.3f}")
        if not (0.06 <= league.bb_rate <= 0.12):
            issues.append(f"League BB% out of range: {league.bb_rate:.3f}")

        # BABIP 역산
        bip_hits = league.single_rate_bip + league.double_rate_bip + league.triple_rate_bip
        bip_no_hr = 1.0 - league.hr_rate_bip
        babip = bip_hits / bip_no_hr if bip_no_hr > 0 else 0
        if not (0.270 <= babip <= 0.320):
            issues.append(f"League BABIP out of range: {babip:.3f}")

        # Park factors
        for park_name, pf in parks.items():
            for attr in ["pf_1b", "pf_2b", "pf_3b", "pf_hr"]:
                val = getattr(pf, attr)
                if not (70 <= val <= 140):
                    issues.append(f"Park {park_name} {attr}={val} out of [70,140]")

        # 팀 구성
        if len(teams) < 28:
            issues.append(f"Too few teams: {len(teams)} (expected 30)")
        for team_id, team in teams.items():
            if len(team.lineup) < 9:
                issues.append(f"Team {team_id} lineup has {len(team.lineup)} batters (need 9)")
            if len(team.bullpen) < 4:
                issues.append(f"Team {team_id} bullpen has {len(team.bullpen)} (need ≥4)")

        if issues:
            for issue in issues:
                logger.warning("Validation: %s", issue)
        else:
            logger.info("All validation checks passed")
