"""DailyDataPipeline — MLB 일일 경기 데이터 수집.

하위 호환성을 위해 기존 인터페이스를 유지합니다.
DailyGame, DailyResult는 daily.pipelines.base에서 re-export.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path

from data.leagues.mlb.teams import TEAM_IDS as MLB_TEAM_IDS
from daily.pipelines.base import DailyGame, DailyResult

logger = logging.getLogger(__name__)

# re-export for backward compatibility
__all__ = ["DailyGame", "DailyResult", "DailyDataPipeline"]

_MLB_ID_TO_ABBR = {v: k for k, v in MLB_TEAM_IDS.items()}


class DailyDataPipeline:
    """MLB Stats API에서 일일 경기 데이터를 수집."""

    league_id = "mlb"

    def __init__(self, cache_dir: str = "cache/daily/"):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_games(self, target_date: date | None = None) -> list[DailyGame]:
        """특정 날짜의 경기 목록 + probable pitcher 수집."""
        if target_date is None:
            target_date = date.today()

        date_str = target_date.isoformat()
        cache_path = self._cache_dir / f"mlb_games_{date_str}.json"

        # 캐시 확인 (당일이면 캐시 무효화 — 선발 변경 가능)
        if cache_path.exists() and target_date != date.today():
            logger.info("Loading cached MLB games: %s", cache_path)
            with open(cache_path) as f:
                raw = json.load(f)
            return [DailyGame(**g) for g in raw]

        import statsapi

        logger.info("Fetching MLB games for %s...", date_str)

        sched = statsapi.get("schedule", {
            "sportId": 1,
            "date": date_str,
            "hydrate": "probablePitcher,linescore,decisions",
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
                        et = dt - timedelta(hours=4)
                        game_time = et.strftime("%H:%M")
                    except (ValueError, TypeError):
                        pass

                venue = g.get("venue", {}).get("name", "")

                games.append(DailyGame(
                    game_id=g["gamePk"],
                    league_id="mlb",
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
                    game_datetime_utc=game_datetime,
                ))

        logger.info("Found %d MLB games for %s", len(games), date_str)

        # 캐시 저장
        with open(cache_path, "w") as f:
            json.dump([asdict(g) for g in games], f, indent=2)

        return games

    def fetch_today(self) -> list[DailyGame]:
        return self.fetch_games(date.today())

    def fetch_yesterday_results(self) -> list[DailyResult]:
        """어제 경기 결과 (linescore + decisions 포함)."""
        yesterday = date.today() - timedelta(days=1)
        date_str = yesterday.isoformat()
        cache_path = self._cache_dir / f"mlb_results_{date_str}.json"

        if cache_path.exists():
            logger.info("Loading cached MLB results: %s", cache_path)
            with open(cache_path) as f:
                raw = json.load(f)
            return [DailyResult(**r) for r in raw]

        import statsapi

        sched = statsapi.get("schedule", {
            "sportId": 1,
            "date": date_str,
            "hydrate": "probablePitcher,linescore,decisions",
        })

        results: list[DailyResult] = []
        for date_entry in sched.get("dates", []):
            for g in date_entry.get("games", []):
                game_type = g.get("gameType", "")
                if game_type not in ("R", "S"):
                    continue

                status = g.get("status", {}).get("detailedState", "")
                if status not in ("Final", "Completed Early", "Game Over"):
                    continue

                teams = g.get("teams", {})
                away_info = teams.get("away", {})
                home_info = teams.get("home", {})

                away_abbr = _MLB_ID_TO_ABBR.get(away_info.get("team", {}).get("id"))
                home_abbr = _MLB_ID_TO_ABBR.get(home_info.get("team", {}).get("id"))
                if away_abbr is None or home_abbr is None:
                    continue

                away_score = away_info.get("score", 0)
                home_score = home_info.get("score", 0)
                winner = "away" if away_score > home_score else "home"

                linescore = g.get("linescore", {})
                innings = linescore.get("innings", [])
                away_innings = [inn.get("away", {}).get("runs", 0) for inn in innings]
                home_innings = [inn.get("home", {}).get("runs", 0) for inn in innings]

                away_totals = linescore.get("teams", {}).get("away", {})
                home_totals = linescore.get("teams", {}).get("home", {})

                decisions = g.get("decisions", {})
                wp = decisions.get("winner", {}).get("fullName", "")
                lp = decisions.get("loser", {}).get("fullName", "")
                sv = decisions.get("save", {}).get("fullName", "")

                away_pp = away_info.get("probablePitcher", {})
                home_pp = home_info.get("probablePitcher", {})

                results.append(DailyResult(
                    game_id=g["gamePk"],
                    league_id="mlb",
                    game_date=g.get("officialDate", date_str),
                    away_team_id=away_abbr,
                    home_team_id=home_abbr,
                    away_score=away_score,
                    home_score=home_score,
                    winner=winner,
                    away_starter_name=away_pp.get("fullName", ""),
                    home_starter_name=home_pp.get("fullName", ""),
                    game_type=game_type,
                    away_innings=away_innings,
                    home_innings=home_innings,
                    away_hits=away_totals.get("hits", 0),
                    home_hits=home_totals.get("hits", 0),
                    away_errors=away_totals.get("errors", 0),
                    home_errors=home_totals.get("errors", 0),
                    winning_pitcher=wp,
                    losing_pitcher=lp,
                    save_pitcher=sv,
                ))

        # Scoring plays + box score
        for r in results:
            try:
                game_data = statsapi.get("game", {"gamePk": r.game_id})
                live = game_data.get("liveData", {})

                plays = live.get("plays", {})
                all_plays = plays.get("allPlays", [])
                for idx in plays.get("scoringPlays", []):
                    if idx >= len(all_plays):
                        continue
                    play = all_plays[idx]
                    rd = play.get("result", {})
                    about = play.get("about", {})
                    r.scoring_plays.append({
                        "inning": about.get("inning", 0),
                        "half": about.get("halfInning", ""),
                        "event": rd.get("event", ""),
                        "description": rd.get("description", ""),
                        "rbi": rd.get("rbi", 0),
                    })

                box = live.get("boxscore", {})
                for side, batters_out, pitchers_out in [
                    ("away", r.away_batters, r.away_pitchers),
                    ("home", r.home_batters, r.home_pitchers),
                ]:
                    team_box = box.get("teams", {}).get(side, {})
                    players = team_box.get("players", {})

                    for pid in team_box.get("battingOrder", []):
                        p = players.get(f"ID{pid}", {})
                        bs = p.get("stats", {}).get("batting", {})
                        if not bs:
                            continue
                        batters_out.append({
                            "name": p.get("person", {}).get("fullName", ""),
                            "pos": p.get("position", {}).get("abbreviation", ""),
                            "ab": bs.get("atBats", 0),
                            "r": bs.get("runs", 0),
                            "h": bs.get("hits", 0),
                            "rbi": bs.get("rbi", 0),
                            "bb": bs.get("baseOnBalls", 0),
                            "k": bs.get("strikeOuts", 0),
                        })

                    for pid in team_box.get("pitchers", []):
                        p = players.get(f"ID{pid}", {})
                        ps = p.get("stats", {}).get("pitching", {})
                        if not ps:
                            continue
                        pitchers_out.append({
                            "name": p.get("person", {}).get("fullName", ""),
                            "ip": ps.get("inningsPitched", "0"),
                            "h": ps.get("hits", 0),
                            "r": ps.get("runs", 0),
                            "er": ps.get("earnedRuns", 0),
                            "bb": ps.get("baseOnBalls", 0),
                            "k": ps.get("strikeOuts", 0),
                            "hr": ps.get("homeRuns", 0),
                        })

            except Exception as e:
                logger.warning("Failed to fetch game data for %s: %s", r.game_id, e)

        logger.info("Fetched game data for %d MLB results", len(results))

        with open(cache_path, "w") as f:
            json.dump([asdict(r) for r in results], f, indent=2)

        return results

    def fetch_schedule_range(
        self,
        start_date: date,
        end_date: date,
    ) -> dict[str, list[DailyGame]]:
        """날짜 범위의 전체 일정 수집."""
        import statsapi

        cache_path = self._cache_dir / f"mlb_schedule_{start_date.year}.json"
        if cache_path.exists():
            logger.info("Loading cached schedule: %s", cache_path)
            with open(cache_path) as f:
                raw = json.load(f)
            result = {}
            for d, games in raw.items():
                result[d] = [DailyGame(**g) for g in games]
            return result

        logger.info("Fetching MLB schedule %s to %s...", start_date, end_date)

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
                    league_id="mlb",
                    game_date=d,
                    game_time=game_time,
                    away_team_id=away_abbr,
                    home_team_id=home_abbr,
                    venue=g.get("venue", {}).get("name", ""),
                    status=g.get("status", {}).get("detailedState", "Scheduled"),
                    game_type=game_type,
                    game_datetime_utc=game_datetime,
                ))
            if day_games:
                by_date[d] = day_games

        logger.info("Fetched %d dates with MLB games", len(by_date))

        serializable = {}
        for d, games in by_date.items():
            serializable[d] = [asdict(g) for g in games]
        with open(cache_path, "w") as f:
            json.dump(serializable, f, indent=2)

        return by_date
