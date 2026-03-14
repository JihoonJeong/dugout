"""리그 설정 — MLB, KBO, NPB."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LeagueConfig:
    league_id: str              # "mlb", "kbo", "npb"
    name: str                   # "MLB", "KBO", "NPB"
    teams: int                  # 30, 10, 12
    season_games: int           # 162, 144, 143
    has_dh: bool                # True, True, True (NPB Central은 V2)
    schedule_source: str        # "mlb_api", "kbo_api", "npb_crawl"
    stats_source: str           # "pybaseball", "kbreport", "npbstats"
    timezone_offset: int        # UTC offset for display: -4(ET), +9(KST/JST)
    season_start: str           # "03-20", "03-28", "03-27"
    season_end: str             # "09-29", "10-15", "10-10"


MLB = LeagueConfig(
    league_id="mlb",
    name="MLB",
    teams=30,
    season_games=162,
    has_dh=True,
    schedule_source="mlb_api",
    stats_source="pybaseball",
    timezone_offset=-4,
    season_start="03-20",
    season_end="09-29",
)

KBO = LeagueConfig(
    league_id="kbo",
    name="KBO",
    teams=10,
    season_games=144,
    has_dh=True,
    schedule_source="kbo_api",
    stats_source="kbreport",
    timezone_offset=9,
    season_start="03-28",
    season_end="10-15",
)

NPB = LeagueConfig(
    league_id="npb",
    name="NPB",
    teams=12,
    season_games=143,
    has_dh=True,  # V1: 센트럴도 DH로 근사
    schedule_source="npb_crawl",
    stats_source="npbstats",
    timezone_offset=9,
    season_start="03-27",
    season_end="10-10",
)

LEAGUES: dict[str, LeagueConfig] = {
    "mlb": MLB,
    "kbo": KBO,
    "npb": NPB,
}


def get_league(league_id: str) -> LeagueConfig:
    cfg = LEAGUES.get(league_id.lower())
    if cfg is None:
        raise ValueError(f"Unknown league: {league_id}. Valid: {list(LEAGUES.keys())}")
    return cfg
