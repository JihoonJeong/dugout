"""Daily pipeline 추상 베이스 클래스."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from core.league_config import LeagueConfig


@dataclass
class DailyGame:
    """모든 리그 공통 경기 정보."""
    game_id: int | str
    league_id: str              # "mlb", "kbo", "npb"
    game_date: str              # "2026-03-25"
    game_time: str              # "19:10" (현지 시간)
    away_team_id: str
    home_team_id: str
    away_starter_mlb_id: Optional[int] = None
    away_starter_name: str = "TBD"
    home_starter_mlb_id: Optional[int] = None
    home_starter_name: str = "TBD"
    status: str = "Scheduled"
    away_score: Optional[int] = None
    home_score: Optional[int] = None
    venue: str = ""
    game_type: str = "R"        # "R" = Regular, "S" = Spring/Preseason
    game_datetime_utc: str = ""  # ISO 8601 UTC


@dataclass
class DailyResult:
    """모든 리그 공통 경기 결과."""
    game_id: int | str
    league_id: str
    game_date: str
    away_team_id: str
    home_team_id: str
    away_score: int
    home_score: int
    winner: str  # "away" | "home"
    away_starter_name: str = ""
    home_starter_name: str = ""
    game_type: str = "R"

    # linescore
    away_innings: list[int] = field(default_factory=list)
    home_innings: list[int] = field(default_factory=list)
    away_hits: int = 0
    home_hits: int = 0
    away_errors: int = 0
    home_errors: int = 0

    # decisions
    winning_pitcher: str = ""
    losing_pitcher: str = ""
    save_pitcher: str = ""

    # scoring plays
    scoring_plays: list[dict] = field(default_factory=list)

    # box score
    away_batters: list[dict] = field(default_factory=list)
    home_batters: list[dict] = field(default_factory=list)
    away_pitchers: list[dict] = field(default_factory=list)
    home_pitchers: list[dict] = field(default_factory=list)


class DailyPipeline(ABC):
    """일일 경기 데이터 수집 추상 인터페이스."""

    def __init__(self, config: LeagueConfig, cache_dir: str = "cache/daily/"):
        self.config = config
        self.league_id = config.league_id

    @abstractmethod
    def fetch_games(self, target_date: date | None = None) -> list[DailyGame]:
        """특정 날짜의 경기 목록 수집."""
        ...

    @abstractmethod
    def fetch_results(self, target_date: date | None = None) -> list[DailyResult]:
        """특정 날짜의 경기 결과 수집."""
        ...

    def fetch_today(self) -> list[DailyGame]:
        return self.fetch_games(date.today())

    def fetch_yesterday_results(self) -> list[DailyResult]:
        from datetime import timedelta
        return self.fetch_results(date.today() - timedelta(days=1))
