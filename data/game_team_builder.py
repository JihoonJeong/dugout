"""경기별 팀 구성 — 선발투수를 교체하여 Team 객체 생성."""

from __future__ import annotations

import logging
from difflib import SequenceMatcher
from typing import Optional

from engine.models import LeagueStats, PitcherStats, Team
from data.pipeline import DugoutData

logger = logging.getLogger(__name__)


def build_game_team(
    team_id: str,
    starter: PitcherStats,
    data: DugoutData,
) -> Team:
    """특정 경기를 위한 팀 구성.

    - 선발투수: 해당 경기의 실제 선발
    - 라인업: 팀 고정 라인업 (Level 1)
    - 불펜: 선발투수를 제외한 팀 RP진
    """
    base_team = data.teams[team_id]
    bullpen = [p for p in base_team.bullpen if p.player_id != starter.player_id]

    return Team(
        team_id=team_id,
        name=base_team.name,
        lineup=base_team.lineup,
        starter=starter,
        bullpen=bullpen if bullpen else base_team.bullpen,
    )


def resolve_starter(
    mlb_id: Optional[int],
    name: str,
    team_id: str,
    data: DugoutData,
    mlb_to_fg: dict[int, str],
) -> tuple[PitcherStats, Optional[str]]:
    """MLB API의 선발투수 정보를 엔진의 PitcherStats로 변환.

    Returns:
        (PitcherStats, fallback_type) — fallback_type은 None이면 직접 매핑 성공.
    """
    # 1. MLB ID → FanGraphs ID 직접 매핑
    if mlb_id is not None:
        fg_id = mlb_to_fg.get(mlb_id)
        if fg_id and fg_id in data.all_pitchers:
            return data.all_pitchers[fg_id], None

    # 2. 이름 exact match (Chadwick에 없는 신인)
    if name:
        for p in data.all_pitchers.values():
            if p.name == name:
                return p, None

    # 3. 이름 fuzzy match
    if name:
        matched = _fuzzy_match_pitcher(name, data.all_pitchers)
        if matched is not None:
            return matched, "fuzzy"

    # 4. 해당 팀 투수진 평균
    if team_id in data.teams:
        team = data.teams[team_id]
        team_pitchers = [team.starter] + team.bullpen
        avg = _average_pitcher(team_pitchers, f"avg_{team_id}", data.league)
        return avg, "team_avg"

    # 5. 리그 평균
    avg = PitcherStats(
        player_id="lg_avg", name="League Average", hand="R",
        pa_against=10000,
        k_rate=data.league.k_rate, bb_rate=data.league.bb_rate,
        hbp_rate=data.league.hbp_rate,
        hr_rate_bip=data.league.hr_rate_bip, go_fo_ratio=data.league.go_fo_ratio,
    )
    return avg, "league_avg"


def build_mlb_to_fg_map(data: DugoutData, id_mapping) -> dict[int, str]:
    """MLB ID → FanGraphs ID 역매핑 생성."""
    import pandas as pd

    fg_to_mlb = dict(zip(id_mapping["key_fangraphs"], id_mapping["key_mlbam"]))
    mlb_to_fg: dict[int, str] = {}

    for fg_id_int, mlb_id in fg_to_mlb.items():
        fg_str = str(int(fg_id_int))
        if fg_str in data.all_pitchers:
            mlb_to_fg[int(mlb_id)] = fg_str

    return mlb_to_fg


def _fuzzy_match_pitcher(
    name: str,
    all_pitchers: dict[str, PitcherStats],
    threshold: float = 0.85,
) -> Optional[PitcherStats]:
    """이름으로 fuzzy match."""
    best_score = 0.0
    best_match = None
    name_lower = name.lower()

    for pitcher in all_pitchers.values():
        score = SequenceMatcher(None, name_lower, pitcher.name.lower()).ratio()
        if score > best_score:
            best_score = score
            best_match = pitcher

    if best_score >= threshold and best_match is not None:
        return best_match

    return None


def _average_pitcher(
    pitchers: list[PitcherStats],
    player_id: str,
    league: LeagueStats,
) -> PitcherStats:
    """투수 리스트의 PA 가중 평균."""
    total_pa = sum(p.pa_against for p in pitchers)
    if total_pa == 0:
        return PitcherStats(
            player_id=player_id, name="Team Average", hand="R",
            pa_against=10000,
            k_rate=league.k_rate, bb_rate=league.bb_rate,
            hbp_rate=league.hbp_rate,
            hr_rate_bip=league.hr_rate_bip, go_fo_ratio=league.go_fo_ratio,
        )

    return PitcherStats(
        player_id=player_id,
        name="Team Average",
        hand="R",
        pa_against=total_pa,
        k_rate=sum(p.k_rate * p.pa_against for p in pitchers) / total_pa,
        bb_rate=sum(p.bb_rate * p.pa_against for p in pitchers) / total_pa,
        hbp_rate=sum(p.hbp_rate * p.pa_against for p in pitchers) / total_pa,
        hr_rate_bip=sum(p.hr_rate_bip * p.pa_against for p in pitchers) / total_pa,
        go_fo_ratio=sum(p.go_fo_ratio * p.pa_against for p in pitchers) / total_pa,
    )
