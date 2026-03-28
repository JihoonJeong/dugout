"""KBO 일일 경기 데이터 수집 파이프라인.

KBO 공식 홈페이지 GameCenter API를 통해 일정/결과를 수집합니다.
API: POST /ws/Main.asmx/GetKboGameList
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

from daily.pipelines.base import DailyGame, DailyResult, DailyPipeline
from core.league_config import KBO

logger = logging.getLogger(__name__)

_KST = timezone(timedelta(hours=9))

# KBO API team codes → our team_id
_KBO_TEAM_CODE = {
    "LG": "LG", "OB": "두산", "HT": "KIA", "SS": "삼성",
    "LT": "롯데", "HH": "한화", "SK": "SSG", "NC": "NC",
    "KT": "KT", "WO": "키움",
    # Korean names (as returned in AWAY_NM / HOME_NM)
    "두산": "두산", "KIA": "KIA", "삼성": "삼성",
    "롯데": "롯데", "한화": "한화", "SSG": "SSG",
    "키움": "키움",
}

_KBO_VENUE = {
    "LG": "잠실야구장", "두산": "잠실야구장",
    "KIA": "광주-기아 챔피언스 필드", "삼성": "대구삼성라이온즈파크",
    "롯데": "사직야구장", "한화": "한화생명이글스파크",
    "SSG": "인천SSG랜더스필드", "NC": "창원NC파크",
    "KT": "수원KT위즈파크", "키움": "고척스카이돔",
}

_API_URL = "https://www.koreabaseball.com/ws/Main.asmx/GetKboGameList"


class KBOPipeline(DailyPipeline):
    """KBO 공식 홈페이지에서 일일 경기 데이터 수집."""

    def __init__(self, cache_dir: str = "cache/daily/"):
        super().__init__(KBO, cache_dir)
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_games(self, target_date: date | None = None) -> list[DailyGame]:
        if target_date is None:
            target_date = date.today()

        date_str = target_date.isoformat()
        cache_path = self._cache_dir / f"kbo_games_{date_str}.json"

        if cache_path.exists() and target_date != date.today():
            logger.info("Loading cached KBO games: %s", cache_path)
            with open(cache_path) as f:
                return [DailyGame(**g) for g in json.load(f)]

        games = self._fetch_from_api(target_date)
        logger.info("Found %d KBO games for %s", len(games), date_str)

        with open(cache_path, "w") as f:
            json.dump([asdict(g) for g in games], f, indent=2, ensure_ascii=False)

        return games

    def fetch_results(self, target_date: date | None = None) -> list[DailyResult]:
        if target_date is None:
            target_date = date.today() - timedelta(days=1)

        date_str = target_date.isoformat()
        cache_path = self._cache_dir / f"kbo_results_{date_str}.json"

        if cache_path.exists():
            logger.info("Loading cached KBO results: %s", cache_path)
            with open(cache_path) as f:
                return [DailyResult(**r) for r in json.load(f)]

        games = self._fetch_from_api(target_date)
        results = []

        # API raw data도 함께 보관 (투수 결정 등 추가 정보용)
        raw_games = self._fetch_from_api(target_date, return_raw=True)
        raw_map = {r.get("G_ID", ""): r for r in raw_games}

        for g in games:
            if g.away_score is None or g.home_score is None:
                continue
            # GAME_STATE_SC "3" = 종료
            if g.status not in ("종료", "Final"):
                continue

            winner = "away" if g.away_score > g.home_score else "home"
            raw = raw_map.get(g.game_id, {})
            results.append(DailyResult(
                game_id=g.game_id,
                league_id="kbo",
                game_date=g.game_date,
                away_team_id=g.away_team_id,
                home_team_id=g.home_team_id,
                away_score=g.away_score,
                home_score=g.home_score,
                winner=winner,
                away_starter_name=g.away_starter_name,
                home_starter_name=g.home_starter_name,
                game_type=g.game_type,
                winning_pitcher=(raw.get("W_PIT_P_NM") or "").strip(),
                losing_pitcher=(raw.get("L_PIT_P_NM") or "").strip(),
                save_pitcher=(raw.get("SV_PIT_P_NM") or "").strip(),
            ))

        logger.info("Found %d KBO results for %s", len(results), date_str)

        if results:
            with open(cache_path, "w") as f:
                json.dump([asdict(r) for r in results], f, indent=2, ensure_ascii=False)

        return results

    def _fetch_from_api(self, target_date: date, return_raw: bool = False) -> list:
        """KBO GameCenter API 호출.

        Args:
            return_raw: True면 원본 dict 리스트 반환, False면 DailyGame 리스트.
        """
        date_str = target_date.strftime("%Y%m%d")

        try:
            resp = httpx.post(
                _API_URL,
                data={"leId": "1", "srId": "0,9", "date": date_str},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": "https://www.koreabaseball.com/Schedule/GameCenter/Main.aspx",
                    "X-Requested-With": "XMLHttpRequest",
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("KBO API failed: %s", e)
            return []

        rows = data.get("game", [])
        if not isinstance(rows, list):
            return []

        if return_raw:
            return rows

        games = []
        for row in rows:
            try:
                games.append(self._parse_row(row, target_date))
            except Exception as e:
                logger.warning("Failed to parse KBO game: %s", e)

        return games

    def _parse_row(self, row: dict, target_date: date) -> DailyGame:
        """API 응답의 단일 게임 row → DailyGame 변환.

        API fields:
            G_ID, G_TM, AWAY_NM, HOME_NM, AWAY_ID, HOME_ID,
            T_SCORE_CN, B_SCORE_CN, GAME_STATE_SC, GAME_SC_NM,
            T_PIT_P_NM (away starter), B_PIT_P_NM (home starter),
            S_NM (venue short name), SR_ID, CANCEL_SC_ID
        """
        away_code = row.get("AWAY_NM", "")
        home_code = row.get("HOME_NM", "")
        away_id = _KBO_TEAM_CODE.get(away_code, away_code)
        home_id = _KBO_TEAM_CODE.get(home_code, home_code)

        game_time = row.get("G_TM", "18:30")
        if len(game_time) == 4 and ":" not in game_time:
            game_time = game_time[:2] + ":" + game_time[2:]

        # Status
        state = str(row.get("GAME_STATE_SC", "1"))
        cancel = str(row.get("CANCEL_SC_ID", "0"))
        status = _parse_status(state, cancel)

        # Scores
        away_score = _parse_int(row.get("T_SCORE_CN"))
        home_score = _parse_int(row.get("B_SCORE_CN"))
        # State "1" (예정) 이면 스코어 무시
        if state == "1":
            away_score = None
            home_score = None

        # Starters
        away_starter = row.get("T_PIT_P_NM", "") or "TBD"
        home_starter = row.get("B_PIT_P_NM", "") or "TBD"

        # Game type
        sr_id = str(row.get("SR_ID", 0))
        game_type = "S" if sr_id == "9" else "R"

        # Venue
        venue_short = row.get("S_NM", "")
        venue = _KBO_VENUE.get(home_id, venue_short)

        # UTC datetime from KST game_time
        try:
            h, m = int(game_time[:2]), int(game_time[3:5])
            kst_dt = datetime(target_date.year, target_date.month, target_date.day, h, m, tzinfo=_KST)
            utc_dt = kst_dt.astimezone(timezone.utc)
            game_datetime_utc = utc_dt.isoformat().replace("+00:00", "Z")
        except (ValueError, IndexError):
            game_datetime_utc = ""

        game_id = row.get("G_ID", f"kbo_{target_date.isoformat()}_{away_id}_{home_id}")

        return DailyGame(
            game_id=game_id,
            league_id="kbo",
            game_date=target_date.isoformat(),
            game_time=game_time,
            away_team_id=away_id,
            home_team_id=home_id,
            away_starter_name=away_starter,
            home_starter_name=home_starter,
            status=status,
            away_score=away_score,
            home_score=home_score,
            venue=venue,
            game_type=game_type,
            game_datetime_utc=game_datetime_utc,
        )


def _parse_status(state: str, cancel: str) -> str:
    if cancel not in ("0", ""):
        return "취소"
    return {
        "1": "Scheduled",
        "2": "In Progress",
        "3": "종료",
    }.get(state, "Scheduled")


def _parse_int(val) -> int | None:
    if val is None or val == "" or val == "-":
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
