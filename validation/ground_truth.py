"""Ground truth 데이터 로드 — 2024 시즌 실제 결과."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from data.constants import MLB_TEAM_IDS

logger = logging.getLogger(__name__)

# MLB team_id → 팀 약칭 역매핑
_MLB_ID_TO_ABBR = {v: k for k, v in MLB_TEAM_IDS.items()}


@dataclass
class ActualResults:
    season: int
    batter_actuals: dict[str, dict] = field(default_factory=dict)
    pitcher_actuals: dict[str, dict] = field(default_factory=dict)
    team_actuals: dict[str, dict] = field(default_factory=dict)
    game_actuals: list[dict] = field(default_factory=list)


def load_actual_results(season: int, cache_dir: str = "cache/") -> ActualResults:
    """2024 시즌 실제 결과를 로드."""
    cache_path = Path(cache_dir) / "validation" / f"actuals_{season}.json"

    if cache_path.exists():
        logger.info("Loading cached actual results: %s", cache_path)
        with open(cache_path) as f:
            raw = json.load(f)
        return ActualResults(
            season=raw["season"],
            batter_actuals=raw["batter_actuals"],
            pitcher_actuals=raw["pitcher_actuals"],
            team_actuals=raw["team_actuals"],
            game_actuals=raw["game_actuals"],
        )

    actual = ActualResults(season=season)

    # 1. 선수 실제 성적 (pybaseball 데이터 재활용)
    actual.batter_actuals = _load_batter_actuals(season, cache_dir)
    actual.pitcher_actuals = _load_pitcher_actuals(season, cache_dir)

    # 2. 팀 실제 성적
    actual.team_actuals = _load_team_actuals(season)

    # 3. 경기별 실제 결과
    actual.game_actuals = _load_game_actuals(season, cache_dir)

    # 캐시 저장
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump({
            "season": actual.season,
            "batter_actuals": actual.batter_actuals,
            "pitcher_actuals": actual.pitcher_actuals,
            "team_actuals": actual.team_actuals,
            "game_actuals": actual.game_actuals,
        }, f)

    return actual


def _load_batter_actuals(season: int, cache_dir: str) -> dict[str, dict]:
    """pybaseball 캐시에서 타자 실제 성적 추출."""
    raw_path = Path(cache_dir) / "raw" / f"batting_stats_{season}.parquet"
    if not raw_path.exists():
        from data.extract import fetch_batting_stats
        df = fetch_batting_stats(season, cache_dir)
    else:
        df = pd.read_parquet(raw_path)

    actuals = {}
    for _, row in df.iterrows():
        try:
            fg_id = str(int(row["IDfg"]))
            pa = int(row["PA"])
            if pa < 1:
                continue

            bb = int(row["BB"])
            ibb = int(row.get("IBB", 0))
            bb_no_ibb = bb - ibb

            actuals[fg_id] = {
                "name": str(row["Name"]),
                "team": str(row["Team"]),
                "pa": pa,
                "k_rate": int(row["SO"]) / pa,
                "bb_rate": bb / pa,
                "bb_rate_no_ibb": bb_no_ibb / pa,
                "hr_rate": int(row["HR"]) / pa,
                "hits": int(row["H"]),
                "hr": int(row["HR"]),
                "doubles": int(row["2B"]),
                "triples": int(row["3B"]),
                "bb": bb,
                "ibb": ibb,
                "so": int(row["SO"]),
                "hbp": int(row["HBP"]),
                "woba": float(row["wOBA"]) if "wOBA" in row.index and pd.notna(row["wOBA"]) else None,
            }
        except Exception as e:
            continue

    logger.info("Loaded %d batter actuals", len(actuals))
    return actuals


def _load_pitcher_actuals(season: int, cache_dir: str) -> dict[str, dict]:
    """pybaseball 캐시에서 투수 실제 성적 추출."""
    raw_path = Path(cache_dir) / "raw" / f"pitching_stats_{season}.parquet"
    if not raw_path.exists():
        from data.extract import fetch_pitching_stats
        df = fetch_pitching_stats(season, cache_dir)
    else:
        df = pd.read_parquet(raw_path)

    actuals = {}
    for _, row in df.iterrows():
        try:
            fg_id = str(int(row["IDfg"]))
            tbf = int(row["TBF"])
            if tbf < 1:
                continue
            actuals[fg_id] = {
                "name": str(row["Name"]),
                "team": str(row["Team"]),
                "tbf": tbf,
                "ip": float(row["IP"]),
                "k_rate": int(row["SO"]) / tbf,
                "bb_rate": int(row["BB"]) / tbf,
                "era": float(row["ERA"]) if "ERA" in row.index and pd.notna(row["ERA"]) else None,
                "fip": float(row["FIP"]) if "FIP" in row.index and pd.notna(row["FIP"]) else None,
            }
        except Exception:
            continue

    logger.info("Loaded %d pitcher actuals", len(actuals))
    return actuals


def _load_team_actuals(season: int) -> dict[str, dict]:
    """MLB Stats API에서 팀 실제 성적 추출."""
    import statsapi

    teams = {}
    standings = statsapi.standings_data(leagueId="103,104", season=season)

    for div_data in standings.values():
        for team in div_data["teams"]:
            team_id_mlb = team["team_id"]
            abbr = _MLB_ID_TO_ABBR.get(team_id_mlb)
            if abbr is None:
                continue
            teams[abbr] = {
                "name": team["name"],
                "wins": team["w"],
                "losses": team["l"],
                "games": team["w"] + team["l"],
            }

    # 득점/실점은 팀 batting/pitching에서 별도로 가져올 수 있지만,
    # V0.1에서는 standings + 시뮬레이션 결과 비교로 충분
    logger.info("Loaded %d team actuals", len(teams))
    return teams


def _load_game_actuals(season: int, cache_dir: str) -> list[dict]:
    """MLB Stats API에서 2024 전 경기 결과 추출."""
    cache_path = Path(cache_dir) / "raw" / f"game_results_{season}.json"

    if cache_path.exists():
        with open(cache_path) as f:
            return json.load(f)

    import statsapi

    logger.info("Fetching %d season game results...", season)

    games = []
    # 시즌을 월별로 나눠서 가져옴
    months = [
        ("03-20", "03-31"), ("04-01", "04-30"), ("05-01", "05-31"),
        ("06-01", "06-30"), ("07-01", "07-31"), ("08-01", "08-31"),
        ("09-01", "09-29"),
    ]

    for start_md, end_md in months:
        start = f"{season}-{start_md}"
        end = f"{season}-{end_md}"
        try:
            sched = statsapi.schedule(start_date=start, end_date=end)
            for g in sched:
                if g.get("status") != "Final":
                    continue
                if g.get("game_type") != "R":  # Regular season only
                    continue

                away_abbr = _MLB_ID_TO_ABBR.get(g["away_id"])
                home_abbr = _MLB_ID_TO_ABBR.get(g["home_id"])
                if away_abbr is None or home_abbr is None:
                    continue

                games.append({
                    "game_id": g["game_id"],
                    "date": g.get("game_date", ""),
                    "away": away_abbr,
                    "home": home_abbr,
                    "away_score": g["away_score"],
                    "home_score": g["home_score"],
                    "winner": "away" if g["away_score"] > g["home_score"] else "home",
                })
        except Exception as e:
            logger.warning("Failed to fetch games %s to %s: %s", start, end, e)

    logger.info("Loaded %d game results", len(games))

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(games, f)

    return games
