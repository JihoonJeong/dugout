"""pybaseball API 호출 + raw 데이터 추출.

pybaseball 의존성은 이 파일에만 격리.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import pandas as pd

from .constants import BATTING_COLS, MLB_TEAM_IDS, PITCHING_COLS

logger = logging.getLogger(__name__)


def fetch_batting_stats(season: int, cache_dir: str | None = None, force: bool = False) -> pd.DataFrame:
    """pybaseball에서 타자 시즌 통계를 가져온다."""
    cache_path = _cache_path(cache_dir, f"batting_stats_{season}.parquet")

    if not force and cache_path and cache_path.exists():
        logger.info("Loading cached batting stats: %s", cache_path)
        return pd.read_parquet(cache_path)

    from pybaseball import batting_stats

    logger.info("Fetching batting stats for %d from FanGraphs...", season)
    df = batting_stats(season, qual=0)

    # 컬럼 존재 확인 & 매핑
    _verify_columns(df, BATTING_COLS, "batting_stats")

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_path)
        logger.info("Cached batting stats to %s", cache_path)

    return df


def fetch_pitching_stats(season: int, cache_dir: str | None = None, force: bool = False) -> pd.DataFrame:
    """pybaseball에서 투수 시즌 통계를 가져온다."""
    cache_path = _cache_path(cache_dir, f"pitching_stats_{season}.parquet")

    if not force and cache_path and cache_path.exists():
        logger.info("Loading cached pitching stats: %s", cache_path)
        return pd.read_parquet(cache_path)

    from pybaseball import pitching_stats

    logger.info("Fetching pitching stats for %d from FanGraphs...", season)
    df = pitching_stats(season, qual=0)

    _verify_columns(df, PITCHING_COLS, "pitching_stats")

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache_path)
        logger.info("Cached pitching stats to %s", cache_path)

    return df


def fetch_player_hands(season: int, cache_dir: str | None = None, force: bool = False) -> dict[int, dict]:
    """MLB Stats API에서 전 선수의 투타 정보를 추출.

    Returns:
        {mlb_id: {"bats": "R"/"L"/"S", "throws": "R"/"L", "name": str}, ...}
    """
    cache_path = _cache_path(cache_dir, f"player_hands_{season}.json")

    if not force and cache_path and cache_path.exists():
        logger.info("Loading cached player hands: %s", cache_path)
        with open(cache_path) as f:
            raw = json.load(f)
        return {int(k): v for k, v in raw.items()}

    import statsapi

    hands: dict[int, dict] = {}

    for team_abbr, team_id in MLB_TEAM_IDS.items():
        try:
            roster = statsapi.get(
                "team_roster",
                {"teamId": team_id, "season": season, "rosterType": "fullSeason", "hydrate": "person"},
            )
            for p in roster.get("roster", []):
                person = p["person"]
                mlb_id = person["id"]
                hands[mlb_id] = {
                    "bats": person.get("batSide", {}).get("code", "R"),
                    "throws": person.get("pitchHand", {}).get("code", "R"),
                    "name": person.get("fullName", ""),
                }
            time.sleep(0.5)  # rate limiting
        except Exception as e:
            logger.warning("Failed to fetch roster for %s (id=%d): %s", team_abbr, team_id, e)
            continue

    logger.info("Fetched hand info for %d players", len(hands))

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump({str(k): v for k, v in hands.items()}, f)

    return hands


def fetch_id_mapping(cache_dir: str | None = None, force: bool = False) -> pd.DataFrame:
    """Chadwick register에서 FanGraphs ID ↔ MLB ID 매핑 테이블 생성.

    Returns:
        DataFrame with columns: key_fangraphs, key_mlbam, name_first, name_last
    """
    cache_path = _cache_path(cache_dir, "id_mapping.parquet")

    if not force and cache_path and cache_path.exists():
        logger.info("Loading cached ID mapping: %s", cache_path)
        return pd.read_parquet(cache_path)

    from pybaseball import chadwick_register

    logger.info("Fetching Chadwick register for ID mapping...")
    reg = chadwick_register()

    # key_fangraphs와 key_mlbam 둘 다 있는 행만
    mapping = reg[["name_first", "name_last", "key_fangraphs", "key_mlbam"]].dropna(
        subset=["key_fangraphs", "key_mlbam"]
    ).copy()
    mapping["key_fangraphs"] = mapping["key_fangraphs"].astype(int)
    mapping["key_mlbam"] = mapping["key_mlbam"].astype(int)

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        mapping.to_parquet(cache_path)

    return mapping


def fetch_statcast_splits(
    season: int,
    cache_dir: str | None = None,
    force: bool = False,
) -> pd.DataFrame:
    """Statcast에서 시즌 전체 pitch-level 데이터를 다운로드하여 platoon splits 집계.

    Returns:
        DataFrame with columns: player_id (MLB ID), role ('batter'/'pitcher'),
        split ('vs_LHP'/'vs_RHP' for batters, 'vs_LHB'/'vs_RHB' for pitchers),
        pa, strikeouts, walks, ibb, hbp, singles, doubles, triples, home_runs,
        ground_balls, fly_balls, line_drives
    """
    cache_path = _cache_path(cache_dir, f"statcast_splits_{season}.parquet")

    if not force and cache_path and cache_path.exists():
        logger.info("Loading cached statcast splits: %s", cache_path)
        return pd.read_parquet(cache_path)

    import pybaseball
    pybaseball.cache.enable()

    logger.info("Fetching Statcast data for %d season (monthly)...", season)

    months = [
        ("03-20", "03-31"), ("04-01", "04-30"), ("05-01", "05-31"),
        ("06-01", "06-30"), ("07-01", "07-31"), ("08-01", "08-31"),
        ("09-01", "09-29"),
    ]

    all_dfs = []
    for start_md, end_md in months:
        start = f"{season}-{start_md}"
        end = f"{season}-{end_md}"
        try:
            logger.info("  Fetching %s to %s...", start, end)
            df = pybaseball.statcast(start, end, verbose=False)
            if df is not None and len(df) > 0:
                all_dfs.append(df)
        except Exception as e:
            logger.warning("Failed to fetch statcast %s to %s: %s", start, end, e)

    if not all_dfs:
        logger.error("No statcast data fetched")
        return pd.DataFrame()

    raw = pd.concat(all_dfs, ignore_index=True)
    logger.info("Total statcast pitches: %d", len(raw))

    # 정규 시즌만
    raw = raw[raw["game_type"] == "R"]

    # PA = events가 non-null인 row만 (완료된 타석)
    pa_df = raw.dropna(subset=["events"]).copy()

    # 이벤트 → 카테고리 매핑
    event_map = {
        "strikeout": "K", "strikeout_double_play": "K",
        "walk": "BB", "intent_walk": "IBB",
        "hit_by_pitch": "HBP",
        "single": "1B", "double": "2B", "triple": "3B", "home_run": "HR",
        "field_out": "OUT", "grounded_into_double_play": "GO",
        "force_out": "OUT", "fielders_choice": "OUT",
        "fielders_choice_out": "OUT", "double_play": "GO",
        "sac_fly": "FO", "sac_fly_double_play": "FO",
        "sac_bunt": "OUT", "sac_bunt_double_play": "OUT",
        "field_error": "OUT", "catcher_interf": "OTHER",
        "triple_play": "OUT",
    }
    pa_df["event_cat"] = pa_df["events"].map(event_map).fillna("OTHER")

    # bb_type → batted ball type (for GB/FB/LD)
    bb_map = {"ground_ball": "GB", "fly_ball": "FB", "line_drive": "LD", "popup": "FB"}
    pa_df["bb_cat"] = pa_df["bb_type"].map(bb_map)

    splits_rows = []

    # --- Batter splits: group by batter + p_throws ---
    for (batter_id, p_throws), grp in pa_df.groupby(["batter", "p_throws"]):
        split = f"vs_L{'HP' if True else ''}" if p_throws == "L" else f"vs_RHP"
        split = "vs_LHP" if p_throws == "L" else "vs_RHP"
        splits_rows.append(_aggregate_split(int(batter_id), "batter", split, grp))

    # --- Pitcher splits: group by pitcher + stand ---
    for (pitcher_id, stand), grp in pa_df.groupby(["pitcher", "stand"]):
        split = "vs_LHB" if stand == "L" else "vs_RHB"
        splits_rows.append(_aggregate_split(int(pitcher_id), "pitcher", split, grp))

    result = pd.DataFrame(splits_rows)
    logger.info("Computed %d split rows", len(result))

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        result.to_parquet(cache_path)
        logger.info("Cached statcast splits to %s", cache_path)

    return result


def _aggregate_split(player_id: int, role: str, split: str, grp: pd.DataFrame) -> dict:
    """Statcast 그룹에서 split 통계를 집계."""
    cats = grp["event_cat"].value_counts()
    bb_cats = grp["bb_cat"].value_counts()
    return {
        "player_id": player_id,
        "role": role,
        "split": split,
        "pa": len(grp),
        "strikeouts": int(cats.get("K", 0)),
        "walks": int(cats.get("BB", 0)),
        "ibb": int(cats.get("IBB", 0)),
        "hbp": int(cats.get("HBP", 0)),
        "singles": int(cats.get("1B", 0)),
        "doubles": int(cats.get("2B", 0)),
        "triples": int(cats.get("3B", 0)),
        "home_runs": int(cats.get("HR", 0)),
        "ground_balls": int(bb_cats.get("GB", 0)),
        "fly_balls": int(bb_cats.get("FB", 0)),
        "line_drives": int(bb_cats.get("LD", 0)),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cache_path(cache_dir: str | None, filename: str) -> Path | None:
    if cache_dir is None:
        return None
    return Path(cache_dir) / "raw" / filename


def _verify_columns(df: pd.DataFrame, col_mapping: dict, source_name: str) -> None:
    """필요한 컬럼이 DataFrame에 존재하는지 확인."""
    missing = []
    for field, col in col_mapping.items():
        if col not in df.columns:
            missing.append(f"{field} → {col}")
    if missing:
        logger.warning(
            "%s: missing columns: %s. Available: %s",
            source_name,
            missing,
            list(df.columns[:30]),
        )
