"""KBO 선수 스탯 크롤러.

KBO 공식 홈페이지 Record 페이지에서 타자/투수 시즌 스탯을 수집합니다.
ASP.NET __doPostBack 기반 페이지네이션을 처리합니다.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_BATTING_URL = "https://www.koreabaseball.com/Record/Player/HitterBasic/BasicOld.aspx"
_PITCHING_URL = "https://www.koreabaseball.com/Record/Player/PitcherBasic/BasicOld.aspx"

_ASP_PREFIX = "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents"

# KBO team codes used by the record page
KBO_TEAM_CODES = ["OB", "LT", "SS", "WO", "LG", "HH", "SK", "NC", "KT", "HT"]

# Map record page team codes → our team_id
_TEAM_CODE_TO_ID = {
    "OB": "두산", "LT": "롯데", "SS": "삼성", "WO": "키움",
    "LG": "LG", "HH": "한화", "SK": "SSG", "NC": "NC",
    "KT": "KT", "HT": "KIA",
}

# Map team names (as shown in HTML) → our team_id
_TEAM_NAME_TO_ID = {
    "두산": "두산", "롯데": "롯데", "삼성": "삼성", "키움": "키움",
    "LG": "LG", "한화": "한화", "SSG": "SSG", "NC": "NC",
    "KT": "KT", "KIA": "KIA",
}


@dataclass
class KBOBatterRaw:
    """KBO 타자 원시 스탯."""
    name: str
    team_id: str
    games: int
    pa: int
    ab: int
    hits: int
    doubles: int
    triples: int
    home_runs: int
    rbi: int
    stolen_bases: int
    caught_stealing: int
    walks: int
    hbp: int
    strikeouts: int
    gdp: int
    errors: int
    avg: float


@dataclass
class KBOPitcherRaw:
    """KBO 투수 원시 스탯."""
    name: str
    team_id: str
    era: float
    games: int
    complete_games: int
    shutouts: int
    wins: int
    losses: int
    saves: int
    holds: int
    tbf: int  # total batters faced (= PA against)
    ip: float  # innings pitched (decimal: 5.1 = 5⅓)
    hits: int
    home_runs: int
    walks: int
    hbp: int
    strikeouts: int
    runs: int
    earned_runs: int


def _get_form_fields(html: str) -> tuple[str, str, str]:
    """Extract ASP.NET hidden form fields."""
    vs = re.search(r'id="__VIEWSTATE"\s+value="([^"]+)"', html)
    vg = re.search(r'id="__VIEWSTATEGENERATOR"\s+value="([^"]+)"', html)
    ev = re.search(r'id="__EVENTVALIDATION"\s+value="([^"]+)"', html)
    if not vs or not vg or not ev:
        raise ValueError("Could not extract ASP.NET form fields")
    return vs.group(1), vg.group(1), ev.group(1)


def _parse_table_rows(html: str) -> list[list[str]]:
    """Parse HTML table rows into lists of cell values."""
    rows = re.findall(r'<tr>(.*?)</tr>', html, re.DOTALL)
    results = []
    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        if len(cells) >= 10 and cells[0].isdigit():
            results.append(cells)
    return results


def _parse_ip(ip_str: str) -> float:
    """Parse KBO innings pitched string to float.

    '197 1/3' → 197.333, '173' → 173.0, '5 2/3' → 5.667
    """
    ip_str = ip_str.strip()
    if '/' in ip_str:
        parts = ip_str.split()
        whole = int(parts[0]) if parts[0].isdigit() else 0
        if len(parts) >= 2 and '/' in parts[-1]:
            num, den = parts[-1].split('/')
            frac = int(num) / int(den)
        else:
            frac = 0
        return whole + frac
    try:
        return float(ip_str)
    except ValueError:
        return 0.0


def fetch_batting_stats(
    season: int = 2025,
    cache_dir: str = "cache/raw/",
) -> list[KBOBatterRaw]:
    """KBO 공식 사이트에서 시즌 타자 스탯 수집.

    팀별로 요청하여 전체 선수 데이터를 모읍니다.
    """
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    cache_file = cache_path / f"kbo_batting_{season}.json"

    if cache_file.exists():
        logger.info("Loading cached KBO batting stats: %s", cache_file)
        with open(cache_file) as f:
            return [KBOBatterRaw(**r) for r in json.load(f)]

    logger.info("Fetching KBO %d batting stats from official site...", season)

    session = httpx.Client(follow_redirects=True, timeout=20)
    all_batters: list[KBOBatterRaw] = []
    seen: set[tuple[str, str]] = set()

    try:
        # Initial GET
        resp = session.get(_BATTING_URL, headers={"User-Agent": "Mozilla/5.0"})
        html = resp.text

        # Prime the session: switch to regular season first (default is preseason)
        vs, vg, ev = _get_form_fields(html)
        prime_form = {
            "__EVENTTARGET": f"{_ASP_PREFIX}$ddlSeries$ddlSeries",
            "__EVENTARGUMENT": "", "__LASTFOCUS": "",
            "__VIEWSTATE": vs, "__VIEWSTATEGENERATOR": vg, "__EVENTVALIDATION": ev,
            f"{_ASP_PREFIX}$ddlSeason$ddlSeason": str(season),
            f"{_ASP_PREFIX}$ddlSeries$ddlSeries": "0",
            f"{_ASP_PREFIX}$ddlTeam$ddlTeam": "",
            f"{_ASP_PREFIX}$ddlPos$ddlPos": "",
            f"{_ASP_PREFIX}$hfPage": "1",
            f"{_ASP_PREFIX}$hfOrderByCol": "PA_CN",
            f"{_ASP_PREFIX}$hfOrderBy": "DESC",
        }
        resp_prime = session.post(
            _BATTING_URL, data=prime_form,
            headers={"User-Agent": "Mozilla/5.0", "Referer": _BATTING_URL},
        )
        html = resp_prime.text

        for team_code in KBO_TEAM_CODES:
            try:
                vs, vg, ev = _get_form_fields(html)
                form = {
                    "__EVENTTARGET": f"{_ASP_PREFIX}$ddlSeries$ddlSeries",
                    "__EVENTARGUMENT": "",
                    "__LASTFOCUS": "",
                    "__VIEWSTATE": vs,
                    "__VIEWSTATEGENERATOR": vg,
                    "__EVENTVALIDATION": ev,
                    f"{_ASP_PREFIX}$ddlSeason$ddlSeason": str(season),
                    f"{_ASP_PREFIX}$ddlSeries$ddlSeries": "0",
                    f"{_ASP_PREFIX}$ddlTeam$ddlTeam": team_code,
                    f"{_ASP_PREFIX}$ddlPos$ddlPos": "",
                    f"{_ASP_PREFIX}$hfPage": "1",
                    f"{_ASP_PREFIX}$hfOrderByCol": "PA_CN",
                    f"{_ASP_PREFIX}$hfOrderBy": "DESC",
                }

                resp2 = session.post(
                    _BATTING_URL, data=form,
                    headers={"User-Agent": "Mozilla/5.0", "Referer": _BATTING_URL},
                )
                html = resp2.text
                rows = _parse_table_rows(html)

                team_id = _TEAM_CODE_TO_ID.get(team_code, team_code)
                count = 0

                for cells in rows:
                    # Columns: rank, name, team, AVG, G, PA, AB, H, 2B, 3B, HR, RBI, SB, CS, BB, HBP, SO, GDP, E
                    name = cells[1]
                    row_team = _TEAM_NAME_TO_ID.get(cells[2], cells[2])

                    key = (name, row_team)
                    if key in seen:
                        continue
                    seen.add(key)

                    try:
                        batter = KBOBatterRaw(
                            name=name,
                            team_id=row_team,
                            avg=float(cells[3]) if cells[3] != '-' else 0.0,
                            games=int(cells[4]),
                            pa=int(cells[5]),
                            ab=int(cells[6]),
                            hits=int(cells[7]),
                            doubles=int(cells[8]),
                            triples=int(cells[9]),
                            home_runs=int(cells[10]),
                            rbi=int(cells[11]),
                            stolen_bases=int(cells[12]),
                            caught_stealing=int(cells[13]),
                            walks=int(cells[14]),
                            hbp=int(cells[15]),
                            strikeouts=int(cells[16]),
                            gdp=int(cells[17]),
                            errors=int(cells[18]) if len(cells) > 18 else 0,
                        )
                        all_batters.append(batter)
                        count += 1
                    except (ValueError, IndexError) as e:
                        logger.debug("Skip batter row: %s", e)

                logger.info("  %s (%s): %d batters", team_code, team_id, count)

            except Exception as e:
                logger.warning("Failed to fetch %s batters: %s", team_code, e)

    finally:
        session.close()

    logger.info("Total KBO batters: %d", len(all_batters))

    # Cache
    with open(cache_file, "w") as f:
        json.dump([b.__dict__ for b in all_batters], f, ensure_ascii=False, indent=2)

    return all_batters


def fetch_pitching_stats(
    season: int = 2025,
    cache_dir: str = "cache/raw/",
) -> list[KBOPitcherRaw]:
    """KBO 공식 사이트에서 시즌 투수 스탯 수집."""
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    cache_file = cache_path / f"kbo_pitching_{season}.json"

    if cache_file.exists():
        logger.info("Loading cached KBO pitching stats: %s", cache_file)
        with open(cache_file) as f:
            return [KBOPitcherRaw(**r) for r in json.load(f)]

    logger.info("Fetching KBO %d pitching stats from official site...", season)

    session = httpx.Client(follow_redirects=True, timeout=20)
    all_pitchers: list[KBOPitcherRaw] = []
    seen: set[tuple[str, str]] = set()

    try:
        resp = session.get(_PITCHING_URL, headers={"User-Agent": "Mozilla/5.0"})
        html = resp.text

        # Prime: switch to regular season
        vs, vg, ev = _get_form_fields(html)
        prime_form = {
            "__EVENTTARGET": f"{_ASP_PREFIX}$ddlSeries$ddlSeries",
            "__EVENTARGUMENT": "", "__LASTFOCUS": "",
            "__VIEWSTATE": vs, "__VIEWSTATEGENERATOR": vg, "__EVENTVALIDATION": ev,
            f"{_ASP_PREFIX}$ddlSeason$ddlSeason": str(season),
            f"{_ASP_PREFIX}$ddlSeries$ddlSeries": "0",
            f"{_ASP_PREFIX}$ddlTeam$ddlTeam": "",
            f"{_ASP_PREFIX}$ddlPos$ddlPos": "",
            f"{_ASP_PREFIX}$hfPage": "1",
            f"{_ASP_PREFIX}$hfOrderByCol": "PA_CN",
            f"{_ASP_PREFIX}$hfOrderBy": "DESC",
        }
        resp_prime = session.post(
            _PITCHING_URL, data=prime_form,
            headers={"User-Agent": "Mozilla/5.0", "Referer": _PITCHING_URL},
        )
        html = resp_prime.text

        for team_code in KBO_TEAM_CODES:
            try:
                vs, vg, ev = _get_form_fields(html)
                form = {
                    "__EVENTTARGET": f"{_ASP_PREFIX}$ddlSeries$ddlSeries",
                    "__EVENTARGUMENT": "",
                    "__LASTFOCUS": "",
                    "__VIEWSTATE": vs,
                    "__VIEWSTATEGENERATOR": vg,
                    "__EVENTVALIDATION": ev,
                    f"{_ASP_PREFIX}$ddlSeason$ddlSeason": str(season),
                    f"{_ASP_PREFIX}$ddlSeries$ddlSeries": "0",
                    f"{_ASP_PREFIX}$ddlTeam$ddlTeam": team_code,
                    f"{_ASP_PREFIX}$ddlPos$ddlPos": "",
                    f"{_ASP_PREFIX}$hfPage": "1",
                    f"{_ASP_PREFIX}$hfOrderByCol": "PA_CN",
                    f"{_ASP_PREFIX}$hfOrderBy": "DESC",
                }

                resp2 = session.post(
                    _PITCHING_URL, data=form,
                    headers={"User-Agent": "Mozilla/5.0", "Referer": _PITCHING_URL},
                )
                html = resp2.text
                rows = _parse_table_rows(html)

                team_id = _TEAM_CODE_TO_ID.get(team_code, team_code)
                count = 0

                for cells in rows:
                    # Columns: rank, name, team, ERA, G, CG, SHO, W, L, SV, HLD, WPCT, TBF, IP, H, HR, BB, HBP, SO, R, ER
                    name = cells[1]
                    row_team = _TEAM_NAME_TO_ID.get(cells[2], cells[2])

                    key = (name, row_team)
                    if key in seen:
                        continue
                    seen.add(key)

                    try:
                        pitcher = KBOPitcherRaw(
                            name=name,
                            team_id=row_team,
                            era=float(cells[3]) if cells[3] != '-' else 0.0,
                            games=int(cells[4]),
                            complete_games=int(cells[5]),
                            shutouts=int(cells[6]),
                            wins=int(cells[7]),
                            losses=int(cells[8]),
                            saves=int(cells[9]),
                            holds=int(cells[10]),
                            tbf=int(cells[12]),
                            ip=_parse_ip(cells[13]),
                            hits=int(cells[14]),
                            home_runs=int(cells[15]),
                            walks=int(cells[16]),
                            hbp=int(cells[17]),
                            strikeouts=int(cells[18]),
                            runs=int(cells[19]),
                            earned_runs=int(cells[20]) if len(cells) > 20 else 0,
                        )
                        all_pitchers.append(pitcher)
                        count += 1
                    except (ValueError, IndexError) as e:
                        logger.debug("Skip pitcher row: %s", e)

                logger.info("  %s (%s): %d pitchers", team_code, team_id, count)

            except Exception as e:
                logger.warning("Failed to fetch %s pitchers: %s", team_code, e)

    finally:
        session.close()

    logger.info("Total KBO pitchers: %d", len(all_pitchers))

    with open(cache_file, "w") as f:
        json.dump([p.__dict__ for p in all_pitchers], f, ensure_ascii=False, indent=2)

    return all_pitchers
