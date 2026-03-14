"""시즌 상태 데이터 모델."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScheduledGame:
    """일정에 있는 한 경기."""
    game_date: str  # "2025-03-27"
    away_team_id: str
    home_team_id: str
    away_starter_name: str = ""
    home_starter_name: str = ""

    # 결과 (시뮬 후 채워짐)
    result: Optional[GameResultSummary] = None
    game_mode: str = "sim"  # sim | gameday | live
    live_game_id: Optional[str] = None  # live/gameday 모드용 세션 ID


@dataclass
class GameResultSummary:
    """경기 결과 요약."""
    away_score: int
    home_score: int
    winner: str  # "away" | "home"
    innings: int
    away_hits: int
    home_hits: int
    highlights: list[str] = field(default_factory=list)


@dataclass
class TeamRecord:
    """팀 시즌 성적."""
    team_id: str
    wins: int = 0
    losses: int = 0
    runs_scored: int = 0
    runs_allowed: int = 0

    @property
    def games(self) -> int:
        return self.wins + self.losses

    @property
    def win_pct(self) -> float:
        return self.wins / self.games if self.games > 0 else .000

    @property
    def run_diff(self) -> int:
        return self.runs_scored - self.runs_allowed


@dataclass
class SeasonState:
    """시즌 전체 상태."""
    season_id: str
    season: int
    user_team_id: str
    philosophy: str
    current_date: str  # "2025-03-27"
    day_index: int = 0  # 시즌 몇 번째 날

    # 일정 (날짜 → 경기 리스트)
    schedule: dict[str, list[ScheduledGame]] = field(default_factory=dict)

    # 팀 성적
    records: dict[str, TeamRecord] = field(default_factory=dict)

    # 시즌 종료 여부
    is_complete: bool = False

    @property
    def user_record(self) -> TeamRecord:
        return self.records[self.user_team_id]

    def get_standings(self, division: str | None = None) -> list[TeamRecord]:
        """순위표 (승률 내림차순)."""
        recs = list(self.records.values())
        return sorted(recs, key=lambda r: (-r.win_pct, -r.run_diff))

    def get_games_on_date(self, date: str) -> list[ScheduledGame]:
        return self.schedule.get(date, [])

    def get_next_game_date(self) -> str | None:
        """현재 날짜 이후 경기가 있는 첫 날짜."""
        dates = sorted(self.schedule.keys())
        for d in dates:
            if d >= self.current_date:
                games = self.schedule[d]
                if any(g.result is None for g in games):
                    return d
        return None
