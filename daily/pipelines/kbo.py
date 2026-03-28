"""KBO 일일 경기 데이터 수집 파이프라인.

KBO 공식 홈페이지 GameCenter API를 통해 일정/결과를 수집합니다.
- GetKboGameList: 기본 스케줄 + 점수 + 투수 결정
- GetScoreBoard: 이닝 스코어, 안타, 실책, 관중, 경기 시간
- GetBoxScore: 결승타, 홈런, 루타 등 하이라이트
"""

from __future__ import annotations

import json
import logging
import re
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

_API_BASE = "https://www.koreabaseball.com/ws"
_GAME_LIST_URL = f"{_API_BASE}/Main.asmx/GetKboGameList"
_SCOREBOARD_URL = f"{_API_BASE}/Schedule.asmx/GetScoreBoard"
_BOXSCORE_URL = f"{_API_BASE}/Schedule.asmx/GetBoxScore"

_HTTP_HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": "https://www.koreabaseball.com/Schedule/GameCenter/Main.aspx",
    "X-Requested-With": "XMLHttpRequest",
}


class KBOPipeline(DailyPipeline):
    """KBO 공식 홈페이지에서 일일 경기 데이터 수집."""

    def __init__(self, cache_dir: str = "cache/daily/"):
        super().__init__(KBO, cache_dir)
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    # ── fetch_games ─────────────────────────────────────────

    def fetch_games(self, target_date: date | None = None) -> list[DailyGame]:
        if target_date is None:
            target_date = date.today()

        date_str = target_date.isoformat()
        cache_path = self._cache_dir / f"kbo_games_{date_str}.json"

        if cache_path.exists() and target_date != date.today():
            logger.info("Loading cached KBO games: %s", cache_path)
            with open(cache_path) as f:
                return [DailyGame(**g) for g in json.load(f)]

        games = self._fetch_game_list(target_date)
        logger.info("Found %d KBO games for %s", len(games), date_str)

        with open(cache_path, "w") as f:
            json.dump([asdict(g) for g in games], f, indent=2, ensure_ascii=False)

        return games

    # ── fetch_results ───────────────────────────────────────

    def fetch_results(self, target_date: date | None = None) -> list[DailyResult]:
        if target_date is None:
            target_date = date.today() - timedelta(days=1)

        date_str = target_date.isoformat()
        cache_path = self._cache_dir / f"kbo_results_{date_str}.json"

        if cache_path.exists():
            logger.info("Loading cached KBO results: %s", cache_path)
            with open(cache_path) as f:
                return [DailyResult(**r) for r in json.load(f)]

        # 1) KBO API에서 결과 빌드
        results = self._build_results_from_api(target_date)

        # 2) 폴백: games 캐시에서 종료된 경기 추출
        if not results:
            results = self._build_results_from_games_cache(target_date)

        logger.info("Found %d KBO results for %s", len(results), date_str)

        if results:
            with open(cache_path, "w") as f:
                json.dump([asdict(r) for r in results], f, indent=2, ensure_ascii=False)

        return results

    def _build_results_from_api(self, target_date: date) -> list[DailyResult]:
        """KBO API에서 기본 결과 + 상세 데이터."""
        games = self._fetch_game_list(target_date)
        raw_rows = self._fetch_game_list(target_date, return_raw=True)
        raw_map = {r.get("G_ID", ""): r for r in raw_rows}

        results = []
        for g in games:
            if g.away_score is None or g.home_score is None:
                continue
            if g.status not in ("종료", "Final"):
                continue

            winner = "away" if g.away_score > g.home_score else "home"
            raw = raw_map.get(g.game_id, {})
            result = DailyResult(
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
            )

            # 상세 데이터 추가 (이닝 스코어, 홈런 등)
            self._enrich_result(result, target_date)
            results.append(result)

        return results

    def _enrich_result(self, result: DailyResult, target_date: date) -> None:
        """GetScoreBoard + GetBoxScore로 이닝 스코어, 하이라이트 추가."""
        date_str = target_date.strftime("%Y%m%d")
        season = str(target_date.year)
        sr_id = "9" if result.game_type == "S" else "0"
        params = {
            "gameDate": date_str,
            "gameId": result.game_id,
            "leId": "1",
            "srId": sr_id,
            "seasonId": season,
        }

        # ── ScoreBoard: 이닝 스코어 ──
        try:
            resp = httpx.post(_SCOREBOARD_URL, data=params, headers=_HTTP_HEADERS, timeout=15)
            resp.raise_for_status()
            sb_data = resp.json()
            self._parse_scoreboard(sb_data, result)
        except Exception as e:
            logger.warning("KBO ScoreBoard failed for %s: %s", result.game_id, e)

        # ── BoxScore: 결승타, 홈런 등 하이라이트 ──
        try:
            resp = httpx.post(_BOXSCORE_URL, data=params, headers=_HTTP_HEADERS, timeout=15)
            resp.raise_for_status()
            box_data = resp.json()
            self._parse_boxscore(box_data, result)
        except Exception as e:
            logger.warning("KBO BoxScore failed for %s: %s", result.game_id, e)

    def _parse_scoreboard(self, data: list, result: DailyResult) -> None:
        """ScoreBoard API 응답에서 이닝 스코어 파싱."""
        if len(data) < 2:
            return

        # data[1][0]은 JSON 문자열로 된 linescore 테이블
        try:
            ls_data = json.loads(data[1][0])
        except (json.JSONDecodeError, IndexError, TypeError):
            return

        rows = ls_data.get("rows", [])
        for i, row_obj in enumerate(rows[:2]):
            cells = [c.get("Text", "") for c in row_obj.get("row", [])]
            # cells: [승패, 팀로고+전적, 1, 2, ..., 9, (10, 11, 12), R, H, E, BB]
            if len(cells) < 6:
                continue

            # 이닝 점수: cells[2:-4] (마지막 4개는 R, H, E, BB)
            inning_cells = cells[2:-4]
            innings = []
            for ic in inning_cells:
                ic_clean = ic.strip()
                if ic_clean == "-" or ic_clean == "":
                    break  # 미진행 이닝
                try:
                    innings.append(int(ic_clean))
                except ValueError:
                    innings.append(0)

            # R, H, E, BB (마지막 4개)
            hits = _parse_int(cells[-3]) or 0
            errors = _parse_int(cells[-2]) or 0

            # 첫 번째 행 = away, 두 번째 = home
            if i == 0:
                result.away_innings = innings
                result.away_hits = hits
                result.away_errors = errors
            else:
                result.home_innings = innings
                result.home_hits = hits
                result.home_errors = errors

    def _parse_boxscore(self, data: dict, result: DailyResult) -> None:
        """BoxScore API 응답에서 하이라이트 (결승타, 홈런 등) 파싱."""
        tables = data.get("tables", [])
        if not tables:
            return

        for table in tables:
            for row_obj in table.get("rows", []):
                cells = row_obj.get("row", [])
                if len(cells) < 2:
                    continue
                label = cells[0].get("Text", "").strip()
                value = cells[1].get("Text", "").strip()
                if not label or not value:
                    continue

                # 홈런, 결승타 등을 scoring_plays에 추가
                if label in ("홈런", "결승타", "3루타", "2루타"):
                    result.scoring_plays.append({
                        "inning": 0,
                        "half": "",
                        "event": label,
                        "description": re.sub(r'\r?\n', ' ', value).strip(),
                        "rbi": 0,
                    })

    def _build_results_from_games_cache(self, target_date: date) -> list[DailyResult]:
        """Games 캐시에서 종료된 경기를 결과로 변환 (폴백)."""
        cache_path = self._cache_dir / f"kbo_games_{target_date.isoformat()}.json"
        if not cache_path.exists():
            return []

        logger.info("Extracting results from KBO games cache: %s", cache_path)
        results = []
        with open(cache_path) as f:
            for g in json.load(f):
                if g.get("status") not in ("종료", "Final"):
                    continue
                if g.get("away_score") is None:
                    continue
                winner = "away" if g["away_score"] > g["home_score"] else "home"
                results.append(DailyResult(
                    game_id=g["game_id"], league_id="kbo",
                    game_date=g["game_date"],
                    away_team_id=g["away_team_id"], home_team_id=g["home_team_id"],
                    away_score=g["away_score"], home_score=g["home_score"],
                    winner=winner,
                    away_starter_name=g.get("away_starter_name", ""),
                    home_starter_name=g.get("home_starter_name", ""),
                    game_type=g.get("game_type", "R"),
                ))
        return results

    # ── KBO GameList API ────────────────────────────────────

    def _fetch_game_list(self, target_date: date, return_raw: bool = False) -> list:
        """KBO GetKboGameList API 호출."""
        date_str = target_date.strftime("%Y%m%d")

        try:
            resp = httpx.post(
                _GAME_LIST_URL,
                data={"leId": "1", "srId": "0,9", "date": date_str},
                headers=_HTTP_HEADERS,
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
        """API 응답의 단일 게임 row → DailyGame 변환."""
        away_code = row.get("AWAY_NM", "")
        home_code = row.get("HOME_NM", "")
        away_id = _KBO_TEAM_CODE.get(away_code, away_code)
        home_id = _KBO_TEAM_CODE.get(home_code, home_code)

        game_time = row.get("G_TM", "18:30")
        if len(game_time) == 4 and ":" not in game_time:
            game_time = game_time[:2] + ":" + game_time[2:]

        state = str(row.get("GAME_STATE_SC", "1"))
        cancel = str(row.get("CANCEL_SC_ID", "0"))
        status = _parse_status(state, cancel)

        away_score = _parse_int(row.get("T_SCORE_CN"))
        home_score = _parse_int(row.get("B_SCORE_CN"))
        if state == "1":
            away_score = None
            home_score = None

        away_starter = row.get("T_PIT_P_NM", "") or "TBD"
        home_starter = row.get("B_PIT_P_NM", "") or "TBD"

        sr_id = str(row.get("SR_ID", 0))
        game_type = "S" if sr_id == "9" else "R"

        venue_short = row.get("S_NM", "")
        venue = _KBO_VENUE.get(home_id, venue_short)

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
