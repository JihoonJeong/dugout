"""경기 일정 + 선발투수 추출 (MLB Stats API)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from .constants import MLB_TEAM_IDS

logger = logging.getLogger(__name__)

# MLB API team_id → 팀 약칭 역매핑
_MLB_ID_TO_ABBR = {v: k for k, v in MLB_TEAM_IDS.items()}


@dataclass
class GameRecord:
    game_id: int
    date: str  # "2024-04-15"
    away_team_id: str  # "NYY"
    home_team_id: str  # "BOS"
    away_starter_mlb_id: Optional[int]  # MLB API player ID
    away_starter_name: str
    home_starter_mlb_id: Optional[int]
    home_starter_name: str
    away_score: Optional[int]
    home_score: Optional[int]
    status: str  # "Final", "Completed Early", etc.

    # 시뮬레이션 결과 (나중에 채워짐)
    sim_away_win_pct: Optional[float] = None
    sim_avg_away_runs: Optional[float] = None
    sim_avg_home_runs: Optional[float] = None

    # Fallback 정보
    away_starter_fallback: Optional[str] = None  # None, "fuzzy", "team_avg", "league_avg"
    home_starter_fallback: Optional[str] = None


def fetch_season_schedule(
    season: int,
    cache_dir: str = "cache/",
) -> list[GameRecord]:
    """시즌 전체 일정 + 선발투수 + 결과를 추출.

    캐시가 있으면 API 호출 스킵.
    """
    cache_path = Path(cache_dir) / f"schedule_{season}.json"

    if cache_path.exists():
        logger.info("Loading cached schedule: %s", cache_path)
        with open(cache_path) as f:
            raw = json.load(f)
        return [GameRecord(**g) for g in raw]

    import statsapi

    logger.info("Fetching %d season schedule from MLB Stats API...", season)

    months = [
        ("03-20", "03-31"), ("04-01", "04-30"), ("05-01", "05-31"),
        ("06-01", "06-30"), ("07-01", "07-31"), ("08-01", "08-31"),
        ("09-01", "09-29"),
    ]

    games: list[GameRecord] = []

    for start_md, end_md in months:
        start = f"{season}-{start_md}"
        end = f"{season}-{end_md}"
        try:
            sched = statsapi.get("schedule", {
                "sportId": 1,
                "startDate": start,
                "endDate": end,
                "hydrate": "probablePitcher",
            })

            for date_entry in sched.get("dates", []):
                for g in date_entry.get("games", []):
                    game_type = g.get("gameType", "")
                    if game_type != "R":
                        continue

                    status = g.get("status", {}).get("detailedState", "")
                    if status not in ("Final", "Completed Early"):
                        continue

                    teams = g.get("teams", {})
                    away_info = teams.get("away", {})
                    home_info = teams.get("home", {})

                    away_team_id_mlb = away_info.get("team", {}).get("id")
                    home_team_id_mlb = home_info.get("team", {}).get("id")
                    away_abbr = _MLB_ID_TO_ABBR.get(away_team_id_mlb)
                    home_abbr = _MLB_ID_TO_ABBR.get(home_team_id_mlb)

                    if away_abbr is None or home_abbr is None:
                        continue

                    away_pp = away_info.get("probablePitcher", {})
                    home_pp = home_info.get("probablePitcher", {})

                    away_score = away_info.get("score")
                    home_score = home_info.get("score")

                    games.append(GameRecord(
                        game_id=g["gamePk"],
                        date=g.get("officialDate", g.get("gameDate", "")[:10]),
                        away_team_id=away_abbr,
                        home_team_id=home_abbr,
                        away_starter_mlb_id=away_pp.get("id"),
                        away_starter_name=away_pp.get("fullName", ""),
                        home_starter_mlb_id=home_pp.get("id"),
                        home_starter_name=home_pp.get("fullName", ""),
                        away_score=away_score,
                        home_score=home_score,
                        status=status,
                    ))

        except Exception as e:
            logger.warning("Failed to fetch schedule %s to %s: %s", start, end, e)

    logger.info("Fetched %d game records for %d", len(games), season)

    # 캐시 저장
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump([asdict(g) for g in games], f)
    logger.info("Cached schedule to %s", cache_path)

    return games
