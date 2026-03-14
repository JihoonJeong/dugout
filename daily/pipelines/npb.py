"""NPB 일일 경기 데이터 수집 파이프라인.

NPB 공식 사이트(npb.jp)에서 월간 상세 스케줄 페이지를 파싱합니다.
URL: https://npb.jp/games/{year}/schedule_{month:02d}_detail.html
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

_NPB_SCHEDULE_URL = "https://npb.jp/games/{year}/schedule_{month:02d}_detail.html"


class NPBPipeline(DailyPipeline):
    """NPB.jp 공식 사이트에서 일일 경기 데이터 수집."""

    def __init__(self, cache_dir: str = "cache/daily/"):
        super().__init__(NPB, cache_dir)
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_games(self, target_date: date | None = None) -> list[DailyGame]:
        if target_date is None:
            target_date = date.today()

        date_str = target_date.isoformat()
        cache_path = self._cache_dir / f"npb_games_{date_str}.json"

        if cache_path.exists() and target_date != date.today():
            logger.info("Loading cached NPB games: %s", cache_path)
            with open(cache_path) as f:
                return [DailyGame(**g) for g in json.load(f)]

        games = self._fetch_from_npb_jp(target_date)
        logger.info("Found %d NPB games for %s", len(games), date_str)

        with open(cache_path, "w") as f:
            json.dump([asdict(g) for g in games], f, indent=2, ensure_ascii=False)

        return games

    def fetch_results(self, target_date: date | None = None) -> list[DailyResult]:
        if target_date is None:
            target_date = date.today() - timedelta(days=1)

        date_str = target_date.isoformat()
        cache_path = self._cache_dir / f"npb_results_{date_str}.json"

        if cache_path.exists():
            logger.info("Loading cached NPB results: %s", cache_path)
            with open(cache_path) as f:
                return [DailyResult(**r) for r in json.load(f)]

        games = self._fetch_from_npb_jp(target_date)
        results = []

        for g in games:
            if g.away_score is None or g.home_score is None:
                continue

            winner = "away" if g.away_score > g.home_score else "home"
            results.append(DailyResult(
                game_id=g.game_id,
                league_id="npb",
                game_date=g.game_date,
                away_team_id=g.away_team_id,
                home_team_id=g.home_team_id,
                away_score=g.away_score,
                home_score=g.home_score,
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

    def _fetch_from_npb_jp(self, target_date: date) -> list[DailyGame]:
        """NPB.jp 월간 상세 스케줄 페이지에서 특정 날짜 경기를 추출."""
        url = _NPB_SCHEDULE_URL.format(year=target_date.year, month=target_date.month)

        try:
            resp = httpx.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Accept-Language": "ja-JP,ja;q=0.9",
                },
                timeout=15,
                follow_redirects=True,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("NPB.jp request failed: %s", e)
            return []

        return self._parse_schedule_html(resp.text, target_date)

    def _parse_schedule_html(self, html: str, target_date: date) -> list[DailyGame]:
        """NPB.jp 월간 상세 스케줄 HTML 파싱.

        Structure per game row:
            <tr id="dateMMDD">
              <td>
                <div class="team1">Away Team</div>
                <a href="/scores/...">
                  <div class="score1">N</div>
                  <div class="state">-</div>
                  <div class="score2">N</div>
                </a>
                <div class="team2">Home Team</div>
              </td>
              <td>
                <div class="place">Venue</div>
                <div class="time">HH:MM</div>
              </td>
            </tr>
        """
        games = []
        day = target_date.day
        month = target_date.month
        date_id = f"date{month:02d}{day:02d}"

        # Find all rows for this date
        # Rows have id="dateMMDD" — first row for a date may also have the date header
        row_pattern = re.compile(
            rf'<tr[^>]*id="{date_id}"[^>]*>(.*?)</tr>',
            re.DOTALL
        )

        for i, match in enumerate(row_pattern.finditer(html)):
            row_html = match.group(1)

            # Extract team names
            team1_m = re.search(r'<div class="team1">\s*(.+?)\s*</div>', row_html)
            team2_m = re.search(r'<div class="team2">\s*(.+?)\s*</div>', row_html)
            if not team1_m or not team2_m:
                continue

            away_name = team1_m.group(1).strip()
            home_name = team2_m.group(1).strip()

            away_id = _NPB_TEAM_ALIAS.get(away_name)
            home_id = _NPB_TEAM_ALIAS.get(home_name)
            if not away_id or not home_id:
                logger.debug("Unknown NPB team: %s or %s", away_name, home_name)
                continue

            # Extract scores (if game is finished)
            score1_m = re.search(r'<div class="score1">\s*(\d+)\s*</div>', row_html)
            score2_m = re.search(r'<div class="score2">\s*(\d+)\s*</div>', row_html)
            away_score = int(score1_m.group(1)) if score1_m else None
            home_score = int(score2_m.group(1)) if score2_m else None

            # Extract venue and time
            place_m = re.search(r'<div class="place">\s*(.+?)\s*</div>', row_html)
            time_m = re.search(r'<div class="time">\s*(\d+:\d+)\s*</div>', row_html)

            venue_text = place_m.group(1).strip() if place_m else ""
            game_time = time_m.group(1) if time_m else "18:00"

            # Use home team's venue if available, otherwise use page text
            venue = _NPB_VENUE.get(home_id, venue_text)

            # Determine game type (regular vs open-sen/pre-season)
            game_type = "R"
            # Open-sen (オープン戦) games are typically before late March
            if target_date.month < 3 or (target_date.month == 3 and target_date.day < 25):
                game_type = "S"

            # Build UTC from JST
            try:
                h, m = int(game_time[:2]), int(game_time[3:5])
                jst_dt = datetime(target_date.year, target_date.month, target_date.day, h, m, tzinfo=_JST)
                utc_dt = jst_dt.astimezone(timezone.utc)
                game_datetime_utc = utc_dt.isoformat().replace("+00:00", "Z")
            except (ValueError, IndexError):
                game_datetime_utc = ""

            game_id = f"npb_{target_date.isoformat()}_{away_id}_{home_id}"

            games.append(DailyGame(
                game_id=game_id,
                league_id="npb",
                game_date=target_date.isoformat(),
                game_time=game_time,
                away_team_id=away_id,
                home_team_id=home_id,
                venue=venue,
                status="Scheduled" if away_score is None else "Final",
                away_score=away_score,
                home_score=home_score,
                game_type=game_type,
                game_datetime_utc=game_datetime_utc,
            ))

        return games
