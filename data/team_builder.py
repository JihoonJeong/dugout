"""팀 구성 로직."""

from __future__ import annotations

import logging
from typing import Optional

from engine.models import BatterStats, PitcherStats, Team
from .constants import TEAM_MAPPING
from .transform import PitcherIntermediate

logger = logging.getLogger(__name__)


def build_team(
    team_id: str,
    all_batters: dict[str, BatterStats],
    all_pitchers: dict[str, PitcherStats],
    pitcher_roles: dict[str, str],  # player_id → "SP" | "RP"
    pitcher_ips: dict[str, float],  # player_id → IP
) -> Optional[Team]:
    """팀 구성. 선발 라인업, 선발 투수, 불펜을 자동 배치.

    Args:
        team_id: 팀 약칭 (NYY, LAD 등)
        all_batters: 전체 타자 dict (team 필터링 전)
        all_pitchers: 전체 투수 dict (team 필터링 전)
        pitcher_roles: 투수 역할 매핑
        pitcher_ips: 투수 이닝 매핑
    """
    team_info = TEAM_MAPPING.get(team_id)
    if team_info is None:
        logger.warning("Unknown team: %s", team_id)
        return None

    # 해당 팀 소속 선수 필터
    # BatterStats/PitcherStats에 team 필드가 없으므로
    # 파이프라인에서 team 매핑을 별도로 전달받음
    # → pipeline.py에서 team별로 분류하여 호출

    # 라인업: PA 상위 9명
    team_batters = list(all_batters.values())
    lineup = sorted(team_batters, key=lambda b: b.pa, reverse=True)[:9]

    if len(lineup) < 9:
        logger.warning("Team %s has only %d batters (need 9)", team_id, len(lineup))
        if len(lineup) == 0:
            return None

    # 투수 분류
    team_pitcher_list = list(all_pitchers.values())
    starters = [p for p in team_pitcher_list if pitcher_roles.get(p.player_id) == "SP"]
    relievers = [p for p in team_pitcher_list if pitcher_roles.get(p.player_id) == "RP"]

    # 선발: IP 최다
    if starters:
        starter = max(starters, key=lambda p: pitcher_ips.get(p.player_id, 0))
    elif team_pitcher_list:
        starter = max(team_pitcher_list, key=lambda p: pitcher_ips.get(p.player_id, 0))
        logger.warning("Team %s has no SP, using top IP pitcher as starter", team_id)
    else:
        logger.warning("Team %s has no pitchers", team_id)
        return None

    # 불펜: IP 상위 5명 (선발 제외)
    bullpen_candidates = [p for p in relievers if p.player_id != starter.player_id]
    if len(bullpen_candidates) < 4:
        # 불펜 부족 시 선발에서 보충
        extra = [p for p in starters if p.player_id != starter.player_id]
        bullpen_candidates.extend(extra)
    bullpen = sorted(bullpen_candidates, key=lambda p: pitcher_ips.get(p.player_id, 0), reverse=True)[:5]

    return Team(
        team_id=team_id,
        name=team_info["name"],
        lineup=lineup,
        starter=starter,
        bullpen=bullpen,
    )
