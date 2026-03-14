"""DailyDataPipeline — 오늘 경기 + 어제 결과 수집."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from data.constants import MLB_TEAM_IDS

logger = logging.getLogger(__name__)

_MLB_ID_TO_ABBR = {v: k for k, v in MLB_TEAM_IDS.items()}


@dataclass
class DailyGame:
    """오늘의 경기 정보."""
    game_id: int
    game_date: str  # "2026-03-25"
    game_time: str  # "19:10" (ET)
    away_team_id: str
    home_team_id: str
    away_starter_mlb_id: Optional[int] = None
    away_starter_name: str = "TBD"
    home_starter_mlb_id: Optional[int] = None
    home_starter_name: str = "TBD"
    status: str = "Scheduled"  # Scheduled, In Progress, Final
    away_score: Optional[int] = None
    home_score: Optional[int] = None
    venue: str = ""
    game_type: str = "R"  # "R" = Regular, "S" = Spring Training


@dataclass
class DailyResult:
    """어제의 경기 결과."""
    game_id: int
    game_date: str
    away_team_id: str
    home_team_id: str
    away_score: int
    home_score: int
    winner: str  # "away" | "home"
    away_starter_name: str = ""
    home_starter_name: str = ""


class DailyDataPipeline:
    """MLB Stats API에서 일일 경기 데이터를 수집."""

    def __init__(self, cache_dir: str = "cache/daily/"):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_games(self, target_date: date | None = None) -> list[DailyGame]:
        """특정 날짜의 경기 목록 + probable pitcher 수집."""
        if target_date is None:
            target_date = date.today()

        date_str = target_date.isoformat()
        cache_path = self._cache_dir / f"games_{date_str}.json"

        # 캐시 확인 (당일이면 캐시 무효화 — 선발 변경 가능)
        if cache_path.exists() and target_date != date.today():
            logger.info("Loading cached games: %s", cache_path)
            with open(cache_path) as f:
                raw = json.load(f)
            return [DailyGame(**g) for g in raw]

        import statsapi

        logger.info("Fetching games for %s from MLB Stats API...", date_str)

        sched = statsapi.get("schedule", {
            "sportId": 1,
            "date": date_str,
            "hydrate": "probablePitcher",
        })

        games: list[DailyGame] = []
        for date_entry in sched.get("dates", []):
            for g in date_entry.get("games", []):
                game_type = g.get("gameType", "")
                if game_type not in ("R", "S"):
                    continue

                teams = g.get("teams", {})
                away_info = teams.get("away", {})
                home_info = teams.get("home", {})

                away_abbr = _MLB_ID_TO_ABBR.get(away_info.get("team", {}).get("id"))
                home_abbr = _MLB_ID_TO_ABBR.get(home_info.get("team", {}).get("id"))
                if away_abbr is None or home_abbr is None:
                    continue

                away_pp = away_info.get("probablePitcher", {})
                home_pp = home_info.get("probablePitcher", {})

                status = g.get("status", {}).get("detailedState", "Scheduled")

                # 경기 시작 시간 파싱
                game_datetime = g.get("gameDate", "")
                game_time = ""
                if game_datetime:
                    try:
                        dt = datetime.fromisoformat(game_datetime.replace("Z", "+00:00"))
                        # UTC → ET (대략 -4h in summer)
                        et = dt - timedelta(hours=4)
                        game_time = et.strftime("%H:%M")
                    except (ValueError, TypeError):
                        pass

                venue = g.get("venue", {}).get("name", "")

                games.append(DailyGame(
                    game_id=g["gamePk"],
                    game_date=g.get("officialDate", date_str),
                    game_time=game_time,
                    away_team_id=away_abbr,
                    home_team_id=home_abbr,
                    away_starter_mlb_id=away_pp.get("id"),
                    away_starter_name=away_pp.get("fullName", "TBD"),
                    home_starter_mlb_id=home_pp.get("id"),
                    home_starter_name=home_pp.get("fullName", "TBD"),
                    status=status,
                    away_score=away_info.get("score"),
                    home_score=home_info.get("score"),
                    venue=venue,
                    game_type=game_type,
                ))

        logger.info("Found %d games for %s", len(games), date_str)

        # 캐시 저장
        with open(cache_path, "w") as f:
            json.dump([asdict(g) for g in games], f, indent=2)

        return games

    def fetch_today(self) -> list[DailyGame]:
        """오늘 경기 목록."""
        return self.fetch_games(date.today())

    def fetch_yesterday_results(self) -> list[DailyResult]:
        """어제 경기 결과."""
        yesterday = date.today() - timedelta(days=1)
        games = self.fetch_games(yesterday)

        results: list[DailyResult] = []
        for g in games:
            if g.status not in ("Final", "Completed Early", "Game Over"):
                continue
            if g.away_score is None or g.home_score is None:
                continue

            winner = "away" if g.away_score > g.home_score else "home"
            results.append(DailyResult(
                game_id=g.game_id,
                game_date=g.game_date,
                away_team_id=g.away_team_id,
                home_team_id=g.home_team_id,
                away_score=g.away_score,
                home_score=g.home_score,
                winner=winner,
                away_starter_name=g.away_starter_name,
                home_starter_name=g.home_starter_name,
            ))

        return results

    def fetch_schedule_range(
        self,
        start_date: date,
        end_date: date,
    ) -> dict[str, list[DailyGame]]:
        """날짜 범위의 전체 일정 수집 (2026 시즌 캐싱용)."""
        import statsapi

        cache_path = self._cache_dir / f"schedule_{start_date.year}.json"
        if cache_path.exists():
            logger.info("Loading cached schedule: %s", cache_path)
            with open(cache_path) as f:
                raw = json.load(f)
            result = {}
            for d, games in raw.items():
                result[d] = [DailyGame(**g) for g in games]
            return result

        logger.info("Fetching schedule %s to %s...", start_date, end_date)

        sched = statsapi.get("schedule", {
            "sportId": 1,
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
        })

        by_date: dict[str, list[DailyGame]] = {}
        for date_entry in sched.get("dates", []):
            d = date_entry["date"]
            day_games = []
            for g in date_entry.get("games", []):
                game_type = g.get("gameType", "")
                if game_type not in ("R", "S"):
                    continue
                teams = g.get("teams", {})
                away_info = teams.get("away", {})
                home_info = teams.get("home", {})
                away_abbr = _MLB_ID_TO_ABBR.get(away_info.get("team", {}).get("id"))
                home_abbr = _MLB_ID_TO_ABBR.get(home_info.get("team", {}).get("id"))
                if away_abbr is None or home_abbr is None:
                    continue

                game_datetime = g.get("gameDate", "")
                game_time = ""
                if game_datetime:
                    try:
                        dt = datetime.fromisoformat(game_datetime.replace("Z", "+00:00"))
                        et = dt - timedelta(hours=4)
                        game_time = et.strftime("%H:%M")
                    except (ValueError, TypeError):
                        pass

                day_games.append(DailyGame(
                    game_id=g["gamePk"],
                    game_date=d,
                    game_time=game_time,
                    away_team_id=away_abbr,
                    home_team_id=home_abbr,
                    venue=g.get("venue", {}).get("name", ""),
                    status=g.get("status", {}).get("detailedState", "Scheduled"),
                    game_type=game_type,
                ))
            if day_games:
                by_date[d] = day_games

        logger.info("Fetched %d dates with games", len(by_date))

        # 캐시 저장
        serializable = {}
        for d, games in by_date.items():
            serializable[d] = [asdict(g) for g in games]
        with open(cache_path, "w") as f:
            json.dump(serializable, f, indent=2)
        logger.info("Cached schedule to %s", cache_path)

        return by_date
