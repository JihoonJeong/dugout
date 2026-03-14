"""리그별 팀/구장 데이터 통합 접근."""

from __future__ import annotations

from data.leagues.mlb.teams import TEAM_MAPPING as MLB_TEAMS, TEAM_SHORT_NAMES as MLB_SHORT
from data.leagues.mlb.parks import PARK_FACTORS as MLB_PARKS
from data.leagues.kbo.teams import TEAM_MAPPING as KBO_TEAMS, TEAM_SHORT_NAMES as KBO_SHORT
from data.leagues.kbo.parks import PARK_FACTORS as KBO_PARKS
from data.leagues.npb.teams import TEAM_MAPPING as NPB_TEAMS, TEAM_SHORT_NAMES as NPB_SHORT
from data.leagues.npb.parks import PARK_FACTORS as NPB_PARKS


_TEAM_MAPPINGS = {"mlb": MLB_TEAMS, "kbo": KBO_TEAMS, "npb": NPB_TEAMS}
_SHORT_NAMES = {"mlb": MLB_SHORT, "kbo": KBO_SHORT, "npb": NPB_SHORT}
_PARK_FACTORS = {"mlb": MLB_PARKS, "kbo": KBO_PARKS, "npb": NPB_PARKS}


def get_team_mapping(league_id: str) -> dict:
    return _TEAM_MAPPINGS.get(league_id, {})


def get_short_names(league_id: str) -> dict:
    return _SHORT_NAMES.get(league_id, {})


def get_park_factors(league_id: str) -> dict:
    return _PARK_FACTORS.get(league_id, {})


def get_all_short_names() -> dict:
    """모든 리그의 짧은 팀명을 합쳐서 반환."""
    merged = {}
    for names in _SHORT_NAMES.values():
        merged.update(names)
    return merged


def get_team_name(league_id: str, team_id: str) -> str:
    """팀 약어 → 영문 이름."""
    mapping = _TEAM_MAPPINGS.get(league_id, {})
    team = mapping.get(team_id, {})
    return team.get("name_en", team.get("name", team_id))


def get_park_name(league_id: str, team_id: str) -> str:
    """팀 약어 → 홈 구장 이름."""
    mapping = _TEAM_MAPPINGS.get(league_id, {})
    team = mapping.get(team_id, {})
    return team.get("park", "")
