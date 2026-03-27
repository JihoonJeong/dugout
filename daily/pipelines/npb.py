"""NPB 일일 경기 데이터 수집 파이프라인.

스케줄: NPB.jp 월간 상세 스케줄 페이지 (시간, 선발투수 등)
결과/점수: Yahoo Japan Baseball (날짜별 조회, 즉시 업데이트)
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
from core.league_config import NPB

logger = logging.getLogger(__name__)

_JST = timezone(timedelta(hours=9))

_YAHOO_SCHEDULE_URL = "https://baseball.yahoo.co.jp/npb/schedule/?date={date}"

_NPB_SCHEDULE_URL = "https://npb.jp/games/{year}/schedule_{month:02d}_detail.html"

# NPB team name mapping (HTML上の表記 → our team_id)
_NPB_TEAM_ALIAS = {
    "巨人": "巨人", "ヤクルト": "ヤクルト", "DeNA": "DeNA",
    "中日": "中日", "阪神": "阪神", "広島": "広島",
    "オリックス": "オリックス", "ソフトバンク": "ソフトバンク",
    "西武": "西武", "楽天": "楽天", "ロッテ": "ロッテ",
    "日本ハム": "日本ハム",
}

_NPB_VENUE = {
    "巨人": "東京ドーム", "阪神": "甲子園球場",
    "中日": "バンテリンドーム", "DeNA": "横浜スタジアム",
    "広島": "MAZDA Zoom-Zoom スタジアム広島", "ヤクルト": "明治神宮野球場",
    "オリックス": "京セラドーム大阪", "ソフトバンク": "みずほPayPayドーム福岡",
    "西武": "ベルーナドーム", "楽天": "楽天モバイルパーク宮城",
    "ロッテ": "ZOZOマリンスタジアム", "日本ハム": "エスコンフィールドHOKKAIDO",
}

_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "ja-JP,ja;q=0.9",
}


def _game_type(target_date: date) -> str:
    """Regular vs pre-season (オープン戦 before late March)."""
    if target_date.month < 3 or (target_date.month == 3 and target_date.day < 25):
        return "S"
    return "R"


class NPBPipeline(DailyPipeline):
    """NPB 일일 경기 데이터 수집 — NPB.jp(스케줄) + Yahoo(결과)."""

    def __init__(self, cache_dir: str = "cache/daily/"):
        super().__init__(NPB, cache_dir)
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    # ── fetch_games ─────────────────────────────────────────

    def fetch_games(self, target_date: date | None = None) -> list[DailyGame]:
        if target_date is None:
            target_date = date.today()

        date_str = target_date.isoformat()
        cache_path = self._cache_dir / f"npb_games_{date_str}.json"

        if cache_path.exists() and target_date != date.today():
            logger.info("Loading cached NPB games: %s", cache_path)
            with open(cache_path) as f:
                return [DailyGame(**g) for g in json.load(f)]

        # NPB.jp에서 스케줄 (시간, 구장 등)
        games = self._fetch_from_npb_jp(target_date)

        # Yahoo에서 점수/status 업데이트
        yahoo_scores = self._fetch_from_yahoo(target_date)
        if yahoo_scores:
            score_map = {(s["team1"], s["team2"]): s for s in yahoo_scores}
            for g in games:
                key = (g.away_team_id, g.home_team_id)
                s = score_map.get(key)
                if s and s["finished"] and g.status == "Scheduled":
                    g.status = "Final"
                    g.away_score = s["score1"]
                    g.home_score = s["score2"]

        logger.info("Found %d NPB games for %s", len(games), date_str)

        with open(cache_path, "w") as f:
            json.dump([asdict(g) for g in games], f, indent=2, ensure_ascii=False)

        return games

    # ── fetch_results ───────────────────────────────────────

    def fetch_results(self, target_date: date | None = None) -> list[DailyResult]:
        if target_date is None:
            target_date = date.today() - timedelta(days=1)

        date_str = target_date.isoformat()
        cache_path = self._cache_dir / f"npb_results_{date_str}.json"

        if cache_path.exists():
            logger.info("Loading cached NPB results: %s", cache_path)
            with open(cache_path) as f:
                return [DailyResult(**r) for r in json.load(f)]

        # 1) Yahoo Japan — 날짜별 조회, 항상 신뢰 가능
        results = self._build_results_from_yahoo(target_date)

        # 2) 폴백: games 캐시에서 Final 경기 추출
        if not results:
            results = self._build_results_from_games_cache(target_date)

        # 3) 최후 폴백: NPB.jp 스케줄 페이지 (점수 반영이 느림)
        if not results:
            logger.info("All sources failed for %s, trying NPB.jp schedule", date_str)
            for g in self._fetch_from_npb_jp(target_date):
                if g.away_score is not None and g.home_score is not None:
                    winner = "away" if g.away_score > g.home_score else "home"
                    results.append(DailyResult(
                        game_id=g.game_id, league_id="npb",
                        game_date=g.game_date,
                        away_team_id=g.away_team_id, home_team_id=g.home_team_id,
                        away_score=g.away_score, home_score=g.home_score,
                        winner=winner,
                        away_starter_name=g.away_starter_name,
                        home_starter_name=g.home_starter_name,
                        game_type=g.game_type,
                    ))

        logger.info("Found %d NPB results for %s", len(results), date_str)

        if results:
            with open(cache_path, "w") as f:
                json.dump([asdict(r) for r in results], f, indent=2, ensure_ascii=False)

        return results

    # ── Yahoo Japan ─────────────────────────────────────────

    def _fetch_from_yahoo(self, target_date: date) -> list[dict] | None:
        """Yahoo Japan Baseball 스케줄 페이지에서 경기 점수 파싱.

        Returns list of dicts: {team1, team2, score1, score2, finished, venue}
        team1/team2 순서는 NPB.jp의 team1/team2와 동일 (homeLogo=team1).
        """
        url = _YAHOO_SCHEDULE_URL.format(date=target_date.isoformat())
        try:
            resp = httpx.get(url, headers=_HTTP_HEADERS, timeout=15, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Yahoo Japan fetch failed: %s", e)
            return None

        return self._parse_yahoo_html(resp.text)

    def _parse_yahoo_html(self, html: str) -> list[dict]:
        """Yahoo Japan Baseball 스케줄 페이지 HTML 파싱.

        Structure per game:
            <p class="bb-score__homeLogo ...">巨人</p>
            <p class="bb-score__awayLogo ...">阪神</p>
            <span class="bb-score__score bb-score__score--left">3</span>
            <span class="bb-score__score bb-score__score--center">-</span>
            <span class="bb-score__score bb-score__score--right">1</span>

        Note: Yahoo's homeLogo = NPB.jp team1 (our away_team_id in game_id).
        """
        results = []

        # Split by game items
        blocks = re.split(r'bb-score__item', html)[1:]

        for block in blocks:
            home_m = re.search(r'homeLogo[^>]*>([^<]+)', block)
            away_m = re.search(r'awayLogo[^>]*>([^<]+)', block)
            if not home_m or not away_m:
                continue

            # Yahoo homeLogo = NPB team1 = our "away" in game_id convention
            team1 = _NPB_TEAM_ALIAS.get(home_m.group(1).strip())
            team2 = _NPB_TEAM_ALIAS.get(away_m.group(1).strip())
            if not team1 or not team2:
                continue

            venue_m = re.search(r'venue">([^<]+)', block)
            venue = venue_m.group(1).strip() if venue_m else ""

            sl = re.search(r'score--left[^>]*>(\d+)', block)
            sr = re.search(r'score--right[^>]*>(\d+)', block)
            finished = sl is not None and sr is not None

            results.append({
                "team1": team1,
                "team2": team2,
                "score1": int(sl.group(1)) if sl else None,
                "score2": int(sr.group(1)) if sr else None,
                "finished": finished,
                "venue": venue,
            })

        return results

    def _build_results_from_yahoo(self, target_date: date) -> list[DailyResult]:
        """Yahoo 데이터로 DailyResult 리스트 생성."""
        yahoo = self._fetch_from_yahoo(target_date)
        if not yahoo:
            return []

        gt = _game_type(target_date)
        results = []
        for s in yahoo:
            if not s["finished"]:
                continue
            game_id = f"npb_{target_date.isoformat()}_{s['team1']}_{s['team2']}"
            winner = "away" if s["score1"] > s["score2"] else "home"
            results.append(DailyResult(
                game_id=game_id,
                league_id="npb",
                game_date=target_date.isoformat(),
                away_team_id=s["team1"],
                home_team_id=s["team2"],
                away_score=s["score1"],
                home_score=s["score2"],
                winner=winner,
                game_type=gt,
            ))
        return results

    def _build_results_from_games_cache(self, target_date: date) -> list[DailyResult]:
        """Games 캐시에서 Final 경기를 결과로 변환."""
        cache_path = self._cache_dir / f"npb_games_{target_date.isoformat()}.json"
        if not cache_path.exists():
            return []

        logger.info("Extracting results from games cache: %s", cache_path)
        results = []
        with open(cache_path) as f:
            for g in json.load(f):
                if g.get("status") != "Final" or g.get("away_score") is None:
                    continue
                winner = "away" if g["away_score"] > g["home_score"] else "home"
                results.append(DailyResult(
                    game_id=g["game_id"], league_id="npb",
                    game_date=g["game_date"],
                    away_team_id=g["away_team_id"], home_team_id=g["home_team_id"],
                    away_score=g["away_score"], home_score=g["home_score"],
                    winner=winner,
                    away_starter_name=g.get("away_starter_name", ""),
                    home_starter_name=g.get("home_starter_name", ""),
                    game_type=g.get("game_type", "R"),
                ))
        return results

    # ── NPB.jp (스케줄 전용) ────────────────────────────────

    def _fetch_from_npb_jp(self, target_date: date) -> list[DailyGame]:
        """NPB.jp 월간 상세 스케줄 페이지에서 특정 날짜 경기를 추출."""
        url = _NPB_SCHEDULE_URL.format(year=target_date.year, month=target_date.month)

        try:
            resp = httpx.get(url, headers=_HTTP_HEADERS, timeout=15, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("NPB.jp request failed: %s", e)
            return []

        return self._parse_schedule_html(resp.text, target_date)

    def _parse_schedule_html(self, html: str, target_date: date) -> list[DailyGame]:
        """NPB.jp 월간 상세 스케줄 HTML 파싱."""
        games = []
        day = target_date.day
        month = target_date.month
        date_id = f"date{month:02d}{day:02d}"
        gt = _game_type(target_date)

        row_pattern = re.compile(
            rf'<tr[^>]*id="{date_id}"[^>]*>(.*?)</tr>',
            re.DOTALL
        )

        for match in row_pattern.finditer(html):
            row_html = match.group(1)

            team1_m = re.search(r'<div class="team1">\s*(.+?)\s*</div>', row_html)
            team2_m = re.search(r'<div class="team2">\s*(.+?)\s*</div>', row_html)
            if not team1_m or not team2_m:
                continue

            away_id = _NPB_TEAM_ALIAS.get(team1_m.group(1).strip())
            home_id = _NPB_TEAM_ALIAS.get(team2_m.group(1).strip())
            if not away_id or not home_id:
                continue

            score1_m = re.search(r'<div class="score1">\s*(\d+)\s*</div>', row_html)
            score2_m = re.search(r'<div class="score2">\s*(\d+)\s*</div>', row_html)
            away_score = int(score1_m.group(1)) if score1_m else None
            home_score = int(score2_m.group(1)) if score2_m else None

            place_m = re.search(r'<div class="place">\s*(.+?)\s*</div>', row_html)
            time_m = re.search(r'<div class="time">\s*(\d+:\d+)\s*</div>', row_html)
            game_time = time_m.group(1) if time_m else "18:00"
            venue = _NPB_VENUE.get(home_id, place_m.group(1).strip() if place_m else "")

            try:
                h, m = int(game_time[:2]), int(game_time[3:5])
                jst_dt = datetime(target_date.year, target_date.month, target_date.day, h, m, tzinfo=_JST)
                game_datetime_utc = jst_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            except (ValueError, IndexError):
                game_datetime_utc = ""

            games.append(DailyGame(
                game_id=f"npb_{target_date.isoformat()}_{away_id}_{home_id}",
                league_id="npb",
                game_date=target_date.isoformat(),
                game_time=game_time,
                away_team_id=away_id,
                home_team_id=home_id,
                venue=venue,
                status="Scheduled" if away_score is None else "Final",
                away_score=away_score,
                home_score=home_score,
                game_type=gt,
                game_datetime_utc=game_datetime_utc,
            ))

        return games
