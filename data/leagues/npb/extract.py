"""NPB 선수 스탯 크롤러.

NPB 공식 사이트(npb.jp) 팀별 개인 성적 페이지에서 타자/투수 시즌 스탯을 수집합니다.
URL: https://npb.jp/bis/{year}/stats/idb1_{team_code}.html (batting)
     https://npb.jp/bis/{year}/stats/idp1_{team_code}.html (pitching)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# NPB team codes used in the stats URL
# Central League
# g=巨人, t=阪神, d=中日, db=DeNA, c=広島, s=ヤクルト
# Pacific League
# b=オリックス, h=ソフトバンク, l=西武, m=ロッテ, e=楽天, f=日本ハム
NPB_TEAM_CODES = ["g", "t", "d", "db", "c", "s", "b", "h", "l", "m", "e", "f"]

_TEAM_CODE_TO_ID = {
    "g": "巨人", "t": "阪神", "d": "中日", "db": "DeNA",
    "c": "広島", "s": "ヤクルト",
    "b": "オリックス", "h": "ソフトバンク", "l": "西武",
    "m": "ロッテ", "e": "楽天", "f": "日本ハム",
}

_BATTING_URL = "https://npb.jp/bis/{year}/stats/idb1_{team_code}.html"
_PITCHING_URL = "https://npb.jp/bis/{year}/stats/idp1_{team_code}.html"


@dataclass
class NPBBatterRaw:
    """NPB 타자 원시 스탯."""
    name: str
    team_id: str
    games: int
    pa: int
    ab: int
    runs: int
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
    avg: float


@dataclass
class NPBPitcherRaw:
    """NPB 투수 원시 스탯."""
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
    tbf: int  # total batters faced
    ip: float  # innings pitched
    hits: int
    home_runs: int
    walks: int
    hbp: int
    strikeouts: int
    runs: int
    earned_runs: int


def _parse_table_rows(html: str) -> list[list[str]]:
    """Parse HTML table rows into lists of cell values."""
    tables = re.findall(r'<table[^>]*>(.*?)</table>', html, re.DOTALL)
    if not tables:
        return []

    # Use the largest table (the stats table)
    table = max(tables, key=len)
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table, re.DOTALL)

    results = []
    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        if not cells:
            continue
        cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
        # Skip header/summary rows — data rows have player name + numeric fields
        if len(cells) >= 10:
            results.append(cells)
    return results


def _clean_name(name: str) -> str:
    """Clean player name: remove handedness marker (*) and normalize whitespace."""
    name = name.lstrip('*')
    # Replace full-width space with regular space, then strip
    name = name.replace('\u3000', ' ').strip()
    return name


def _parse_ip(ip_str: str) -> float:
    """Parse NPB innings pitched string to float.

    '121' → 121.0, '59' → 59.0, '12.1' → 12.333
    NPB uses decimal notation: 59 2/3 shown as partial innings.
    Some pages show plain integers.
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


def _safe_int(val: str) -> int:
    """Parse int, defaulting to 0 for empty/dash values."""
    val = val.strip()
    if not val or val == '-' or val == '－':
        return 0
    try:
        return int(val)
    except ValueError:
        return 0


def _safe_float(val: str) -> float:
    """Parse float, defaulting to 0.0 for empty/dash values."""
    val = val.strip()
    if not val or val == '-' or val == '－':
        return 0.0
    try:
        return float(val)
    except ValueError:
        return 0.0


def fetch_batting_stats(
    season: int = 2025,
    cache_dir: str = "cache/raw/",
) -> list[NPBBatterRaw]:
    """NPB 공식 사이트에서 시즌 타자 스탯 수집 (팀별 페이지)."""
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    cache_file = cache_path / f"npb_batting_{season}.json"

    if cache_file.exists():
        logger.info("Loading cached NPB batting stats: %s", cache_file)
        with open(cache_file) as f:
            return [NPBBatterRaw(**r) for r in json.load(f)]

    logger.info("Fetching NPB %d batting stats from npb.jp...", season)

    all_batters: list[NPBBatterRaw] = []

    for team_code in NPB_TEAM_CODES:
        team_id = _TEAM_CODE_TO_ID[team_code]
        url = _BATTING_URL.format(year=season, team_code=team_code)

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
            logger.warning("Failed to fetch %s batting: %s", team_code, e)
            continue

        rows = _parse_table_rows(resp.text)
        count = 0

        for cells in rows:
            # Columns: Player(0), G(1), PA(2), AB(3), R(4), H(5), 2B(6), 3B(7),
            #          HR(8), TB(9), RBI(10), SB(11), CS(12), SAC(13), SF(14),
            #          BB(15), IBB(16), HBP(17), K(18), GIDP(19), AVG(20), SLG(21), OBP(22)
            try:
                name = _clean_name(cells[0])
                if not name or name in ('合計', '投手合計', 'チーム合計'):
                    continue

                batter = NPBBatterRaw(
                    name=name,
                    team_id=team_id,
                    games=_safe_int(cells[1]),
                    pa=_safe_int(cells[2]),
                    ab=_safe_int(cells[3]),
                    runs=_safe_int(cells[4]),
                    hits=_safe_int(cells[5]),
                    doubles=_safe_int(cells[6]),
                    triples=_safe_int(cells[7]),
                    home_runs=_safe_int(cells[8]),
                    rbi=_safe_int(cells[10]),
                    stolen_bases=_safe_int(cells[11]),
                    caught_stealing=_safe_int(cells[12]),
                    walks=_safe_int(cells[15]),
                    hbp=_safe_int(cells[17]),
                    strikeouts=_safe_int(cells[18]),
                    gdp=_safe_int(cells[19]),
                    avg=_safe_float(cells[20]),
                )
                all_batters.append(batter)
                count += 1
            except (ValueError, IndexError) as e:
                logger.debug("Skip batter row: %s", e)

        logger.info("  %s (%s): %d batters", team_code, team_id, count)

    logger.info("Total NPB batters: %d", len(all_batters))

    with open(cache_file, "w") as f:
        json.dump([b.__dict__ for b in all_batters], f, ensure_ascii=False, indent=2)

    return all_batters


def fetch_pitching_stats(
    season: int = 2025,
    cache_dir: str = "cache/raw/",
) -> list[NPBPitcherRaw]:
    """NPB 공식 사이트에서 시즌 투수 스탯 수집 (팀별 페이지)."""
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    cache_file = cache_path / f"npb_pitching_{season}.json"

    if cache_file.exists():
        logger.info("Loading cached NPB pitching stats: %s", cache_file)
        with open(cache_file) as f:
            return [NPBPitcherRaw(**r) for r in json.load(f)]

    logger.info("Fetching NPB %d pitching stats from npb.jp...", season)

    all_pitchers: list[NPBPitcherRaw] = []

    for team_code in NPB_TEAM_CODES:
        team_id = _TEAM_CODE_TO_ID[team_code]
        url = _PITCHING_URL.format(year=season, team_code=team_code)

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
            logger.warning("Failed to fetch %s pitching: %s", team_code, e)
            continue

        rows = _parse_table_rows(resp.text)
        count = 0

        for cells in rows:
            # Columns: Player(0), G(1), W(2), L(3), SV(4), HLD(5), HP(6),
            #          CG(7), SHO(8), no-walk(9), WPCT(10), TBF(11), IP(12),
            #          H(13), HR(14), BB(15), IBB(16), HBP(17), K(18),
            #          WP(19), BK(20), R(21), ER(22), ERA(23)
            try:
                name = _clean_name(cells[0])
                if not name or name in ('合計', 'チーム合計'):
                    continue

                pitcher = NPBPitcherRaw(
                    name=name,
                    team_id=team_id,
                    games=_safe_int(cells[1]),
                    wins=_safe_int(cells[2]),
                    losses=_safe_int(cells[3]),
                    saves=_safe_int(cells[4]),
                    holds=_safe_int(cells[5]),
                    complete_games=_safe_int(cells[7]),
                    shutouts=_safe_int(cells[8]),
                    tbf=_safe_int(cells[11]),
                    ip=_parse_ip(cells[12]),
                    hits=_safe_int(cells[13]),
                    home_runs=_safe_int(cells[14]),
                    walks=_safe_int(cells[15]),
                    hbp=_safe_int(cells[17]),
                    strikeouts=_safe_int(cells[18]),
                    runs=_safe_int(cells[21]),
                    earned_runs=_safe_int(cells[22]),
                    era=_safe_float(cells[23]),
                )
                all_pitchers.append(pitcher)
                count += 1
            except (ValueError, IndexError) as e:
                logger.debug("Skip pitcher row: %s", e)

        logger.info("  %s (%s): %d pitchers", team_code, team_id, count)

    logger.info("Total NPB pitchers: %d", len(all_pitchers))

    with open(cache_file, "w") as f:
        json.dump([p.__dict__ for p in all_pitchers], f, ensure_ascii=False, indent=2)

    return all_pitchers
