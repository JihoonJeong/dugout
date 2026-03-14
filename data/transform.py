"""Raw DataFrame → Intermediate → Engine-ready 변환."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from engine.models import BatterStats, LeagueStats, PitcherStats
from .constants import BATTING_COLS, PITCHING_COLS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Intermediate data classes
# ---------------------------------------------------------------------------


@dataclass
class BatterIntermediate:
    player_id: str  # FanGraphs ID (문자열)
    mlb_id: Optional[int]
    name: str
    team: str
    hand: str  # "L", "R", "S"
    season: int
    pa: int
    ab: int
    hits: int
    singles: int
    doubles: int
    triples: int
    home_runs: int
    walks: int
    ibb: int
    strikeouts: int
    hbp: int
    ground_balls: int
    fly_balls: int
    line_drives: int


@dataclass
class PitcherIntermediate:
    player_id: str
    mlb_id: Optional[int]
    name: str
    team: str
    hand: str  # "L", "R"
    season: int
    role: str  # "SP" | "RP"
    pa_against: int
    ip: float
    hits_allowed: int
    home_runs_allowed: int
    walks_allowed: int
    ibb: int
    strikeouts: int
    hbp: int
    ground_balls: int
    fly_balls: int


# ---------------------------------------------------------------------------
# Raw → Intermediate
# ---------------------------------------------------------------------------


def transform_batters(
    df: pd.DataFrame,
    id_mapping: pd.DataFrame,
    player_hands: dict[int, dict],
    season: int,
) -> list[BatterIntermediate]:
    """batting_stats DataFrame → BatterIntermediate 리스트."""
    C = BATTING_COLS
    results = []

    # FanGraphs ID → MLB ID 매핑 딕셔너리
    fg_to_mlb = dict(zip(id_mapping["key_fangraphs"], id_mapping["key_mlbam"]))

    for _, row in df.iterrows():
        try:
            fg_id = str(int(row[C["player_id"]]))
            pa = int(row[C["pa"]])
            if pa < 1:
                continue

            mlb_id = fg_to_mlb.get(int(fg_id))

            # 투타 정보: MLB API 데이터에서 조회
            hand = "R"  # default
            if mlb_id and mlb_id in player_hands:
                hand = player_hands[mlb_id].get("bats", "R")

            # singles: pybaseball이 1B 컬럼을 제공하면 사용, 없으면 역산
            if C["singles"] in df.columns:
                singles = int(row[C["singles"]])
            else:
                singles = int(row[C["hits"]]) - int(row[C["doubles"]]) - int(row[C["triples"]]) - int(row[C["home_runs"]])
                singles = max(singles, 0)

            ibb = int(row[C["ibb"]]) if C["ibb"] in df.columns else 0

            results.append(BatterIntermediate(
                player_id=fg_id,
                mlb_id=mlb_id,
                name=str(row[C["name"]]),
                team=str(row[C["team"]]),
                hand=hand,
                season=season,
                pa=pa,
                ab=int(row[C["ab"]]),
                hits=int(row[C["hits"]]),
                singles=singles,
                doubles=int(row[C["doubles"]]),
                triples=int(row[C["triples"]]),
                home_runs=int(row[C["home_runs"]]),
                walks=int(row[C["walks"]]),
                ibb=ibb,
                strikeouts=int(row[C["strikeouts"]]),
                hbp=int(row[C["hbp"]]),
                ground_balls=int(row[C["ground_balls"]]),
                fly_balls=int(row[C["fly_balls"]]),
                line_drives=int(row[C["line_drives"]]),
            ))
        except Exception as e:
            name = row.get(C["name"], "?")
            logger.warning("Failed to transform batter %s: %s", name, e)
            continue

    logger.info("Transformed %d batters", len(results))
    return results


def transform_pitchers(
    df: pd.DataFrame,
    id_mapping: pd.DataFrame,
    player_hands: dict[int, dict],
    season: int,
) -> list[PitcherIntermediate]:
    """pitching_stats DataFrame → PitcherIntermediate 리스트."""
    C = PITCHING_COLS
    results = []

    fg_to_mlb = dict(zip(id_mapping["key_fangraphs"], id_mapping["key_mlbam"]))

    for _, row in df.iterrows():
        try:
            fg_id = str(int(row[C["player_id"]]))
            tbf = int(row[C["pa_against"]])
            if tbf < 1:
                continue

            mlb_id = fg_to_mlb.get(int(fg_id))

            hand = "R"
            if mlb_id and mlb_id in player_hands:
                hand = player_hands[mlb_id].get("throws", "R")

            gs = int(row[C["games_started"]]) if C["games_started"] in df.columns else 0
            role = "SP" if gs > 0 else "RP"

            ibb = int(row[C["ibb"]]) if C["ibb"] in df.columns else 0

            results.append(PitcherIntermediate(
                player_id=fg_id,
                mlb_id=mlb_id,
                name=str(row[C["name"]]),
                team=str(row[C["team"]]),
                hand=hand,
                season=season,
                role=role,
                pa_against=tbf,
                ip=float(row[C["ip"]]),
                hits_allowed=int(row[C["hits_allowed"]]),
                home_runs_allowed=int(row[C["home_runs_allowed"]]),
                walks_allowed=int(row[C["walks_allowed"]]),
                ibb=ibb,
                strikeouts=int(row[C["strikeouts"]]),
                hbp=int(row[C["hbp"]]),
                ground_balls=int(row[C["ground_balls"]]),
                fly_balls=int(row[C["fly_balls"]]),
            ))
        except Exception as e:
            name = row.get(C["name"], "?")
            logger.warning("Failed to transform pitcher %s: %s", name, e)
            continue

    logger.info("Transformed %d pitchers", len(results))
    return results


# ---------------------------------------------------------------------------
# Intermediate → Engine-ready
# ---------------------------------------------------------------------------


def to_batter_stats(bi: BatterIntermediate, league: LeagueStats, splits_data: dict | None = None) -> BatterStats:
    """BatterIntermediate → BatterStats (엔진 소비용)."""
    k_rate = bi.strikeouts / bi.pa
    bb_rate = (bi.walks - bi.ibb) / bi.pa  # IBB 제외: 전략적 선택이지 skill 아님
    hbp_rate = bi.hbp / bi.pa

    # BIP 계산: IBB도 PA를 소비하지만 BIP가 아님 (total BB 사용)
    bip = bi.pa - bi.strikeouts - bi.walks - bi.hbp

    if bip > 0:
        single_rate_bip = bi.singles / bip
        double_rate_bip = bi.doubles / bip
        triple_rate_bip = bi.triples / bip
        hr_rate_bip = bi.home_runs / bip

        # GO/FO 산출
        outs_bip = bip - bi.singles - bi.doubles - bi.triples - bi.home_runs
        total_batted = bi.ground_balls + bi.fly_balls + bi.line_drives

        if total_batted > 0 and outs_bip > 0:
            gb_share = bi.ground_balls / total_batted
            go_count = round(outs_bip * gb_share)
            fo_count = outs_bip - go_count
            go_rate_bip = go_count / bip
            fo_rate_bip = fo_count / bip
        else:
            go_rate_bip = league.go_rate_bip
            fo_rate_bip = league.fo_rate_bip
    else:
        # BIP 없음 → 리그 평균
        single_rate_bip = league.single_rate_bip
        double_rate_bip = league.double_rate_bip
        triple_rate_bip = league.triple_rate_bip
        hr_rate_bip = league.hr_rate_bip
        go_rate_bip = league.go_rate_bip
        fo_rate_bip = league.fo_rate_bip

    # BIP 내 비율 정규화
    bip_total = single_rate_bip + double_rate_bip + triple_rate_bip + hr_rate_bip + go_rate_bip + fo_rate_bip
    if bip_total > 0 and abs(bip_total - 1.0) > 0.001:
        single_rate_bip /= bip_total
        double_rate_bip /= bip_total
        triple_rate_bip /= bip_total
        hr_rate_bip /= bip_total
        go_rate_bip /= bip_total
        fo_rate_bip /= bip_total

    # Floor 처리
    k_rate = max(k_rate, 0.001)
    bb_rate = max(bb_rate, 0.001)
    hbp_rate = max(hbp_rate, 0.001)

    # Platoon splits
    splits = None
    if splits_data and bi.mlb_id:
        splits = _build_batter_splits(bi.mlb_id, splits_data, league)

    return BatterStats(
        player_id=bi.player_id,
        name=bi.name,
        hand=bi.hand,
        pa=bi.pa,
        k_rate=k_rate,
        bb_rate=bb_rate,
        hbp_rate=hbp_rate,
        single_rate_bip=single_rate_bip,
        double_rate_bip=double_rate_bip,
        triple_rate_bip=triple_rate_bip,
        hr_rate_bip=hr_rate_bip,
        go_rate_bip=go_rate_bip,
        fo_rate_bip=fo_rate_bip,
        splits=splits,
    )


def to_pitcher_stats(pi: PitcherIntermediate, league: LeagueStats, splits_data: dict | None = None) -> PitcherStats:
    """PitcherIntermediate → PitcherStats (엔진 소비용)."""
    k_rate = pi.strikeouts / pi.pa_against
    bb_rate = (pi.walks_allowed - pi.ibb) / pi.pa_against  # IBB 제외
    hbp_rate = pi.hbp / pi.pa_against

    # BIP 계산: total BB 사용 (IBB도 non-BIP)
    bip = pi.pa_against - pi.strikeouts - pi.walks_allowed - pi.hbp
    hr_rate_bip = pi.home_runs_allowed / bip if bip > 0 else league.hr_rate_bip

    if pi.fly_balls > 0:
        go_fo_ratio = pi.ground_balls / pi.fly_balls
    else:
        go_fo_ratio = league.go_fo_ratio

    # Floor 처리
    k_rate = max(k_rate, 0.001)
    bb_rate = max(bb_rate, 0.001)
    hbp_rate = max(hbp_rate, 0.001)
    hr_rate_bip = max(hr_rate_bip, 0.001)
    go_fo_ratio = max(go_fo_ratio, 0.1)

    # Platoon splits
    splits = None
    if splits_data and pi.mlb_id:
        splits = _build_pitcher_splits(pi.mlb_id, splits_data, league)

    return PitcherStats(
        player_id=pi.player_id,
        name=pi.name,
        hand=pi.hand,
        pa_against=pi.pa_against,
        k_rate=k_rate,
        bb_rate=bb_rate,
        hbp_rate=hbp_rate,
        hr_rate_bip=hr_rate_bip,
        go_fo_ratio=go_fo_ratio,
        splits=splits,
    )


def calculate_league_stats(all_batters: list[BatterIntermediate], season: int) -> LeagueStats:
    """전체 타자 데이터를 합산하여 리그 평균 산출."""
    total_pa = sum(b.pa for b in all_batters)
    total_k = sum(b.strikeouts for b in all_batters)
    total_bb = sum(b.walks for b in all_batters)
    total_ibb = sum(b.ibb for b in all_batters)
    total_hbp = sum(b.hbp for b in all_batters)
    total_1b = sum(b.singles for b in all_batters)
    total_2b = sum(b.doubles for b in all_batters)
    total_3b = sum(b.triples for b in all_batters)
    total_hr = sum(b.home_runs for b in all_batters)
    total_gb = sum(b.ground_balls for b in all_batters)
    total_fb = sum(b.fly_balls for b in all_batters)
    total_ld = sum(b.line_drives for b in all_batters)

    total_bip = total_pa - total_k - total_bb - total_hbp
    total_outs_bip = total_bip - total_1b - total_2b - total_3b - total_hr
    total_batted = total_gb + total_fb + total_ld

    gb_share = total_gb / total_batted if total_batted > 0 else 0.45
    go_count = round(total_outs_bip * gb_share)
    fo_count = total_outs_bip - go_count

    return LeagueStats(
        season=season,
        k_rate=total_k / total_pa,
        bb_rate=(total_bb - total_ibb) / total_pa,  # IBB 제외
        hbp_rate=total_hbp / total_pa,
        single_rate_bip=total_1b / total_bip,
        double_rate_bip=total_2b / total_bip,
        triple_rate_bip=total_3b / total_bip,
        hr_rate_bip=total_hr / total_bip,
        go_rate_bip=go_count / total_bip,
        fo_rate_bip=fo_count / total_bip,
        go_fo_ratio=total_gb / total_fb if total_fb > 0 else 1.0,
    )


# ---------------------------------------------------------------------------
# Platoon splits helpers
# ---------------------------------------------------------------------------


def prepare_splits_lookup(splits_df) -> dict:
    """Statcast splits DataFrame → {(mlb_id, role, split): row_dict} 조회용 dict."""
    if splits_df is None or len(splits_df) == 0:
        return {}
    lookup = {}
    for _, row in splits_df.iterrows():
        key = (int(row["player_id"]), row["role"], row["split"])
        lookup[key] = row.to_dict()
    return lookup


def _build_batter_splits(mlb_id: int, splits_data: dict, league: LeagueStats) -> dict | None:
    """Statcast splits 데이터에서 타자 platoon splits 구성."""
    vs_lhp = splits_data.get((mlb_id, "batter", "vs_LHP"))
    vs_rhp = splits_data.get((mlb_id, "batter", "vs_RHP"))

    if vs_lhp is None and vs_rhp is None:
        return None

    result = {}
    for split_name, data in [("vs_LHP", vs_lhp), ("vs_RHP", vs_rhp)]:
        if data is None:
            continue
        pa = int(data["pa"])
        if pa < 10:  # 극소 표본 제외
            continue
        result[split_name] = _compute_batter_split_rates(data, league)

    return result if result else None


def _compute_batter_split_rates(data: dict, league: LeagueStats) -> dict:
    """단일 split 데이터에서 타자 rate 스탯 계산."""
    pa = int(data["pa"])
    k = int(data["strikeouts"])
    bb = int(data["walks"])
    ibb = int(data.get("ibb", 0))
    hbp = int(data["hbp"])
    singles = int(data["singles"])
    doubles = int(data["doubles"])
    triples = int(data["triples"])
    hr = int(data["home_runs"])
    gb = int(data["ground_balls"])
    fb = int(data["fly_balls"])
    ld = int(data["line_drives"])

    k_rate = k / pa if pa > 0 else league.k_rate
    bb_rate = (bb - ibb) / pa if pa > 0 else league.bb_rate
    hbp_rate = hbp / pa if pa > 0 else league.hbp_rate

    bip = pa - k - bb - ibb - hbp
    if bip > 0:
        single_rate_bip = singles / bip
        double_rate_bip = doubles / bip
        triple_rate_bip = triples / bip
        hr_rate_bip = hr / bip

        outs_bip = bip - singles - doubles - triples - hr
        total_batted = gb + fb + ld
        if total_batted > 0 and outs_bip > 0:
            gb_share = gb / total_batted
            go_count = round(outs_bip * gb_share)
            fo_count = outs_bip - go_count
            go_rate_bip = go_count / bip
            fo_rate_bip = fo_count / bip
        else:
            go_rate_bip = league.go_rate_bip
            fo_rate_bip = league.fo_rate_bip
    else:
        single_rate_bip = league.single_rate_bip
        double_rate_bip = league.double_rate_bip
        triple_rate_bip = league.triple_rate_bip
        hr_rate_bip = league.hr_rate_bip
        go_rate_bip = league.go_rate_bip
        fo_rate_bip = league.fo_rate_bip

    return {
        "pa": pa,
        "k_rate": max(k_rate, 0.001),
        "bb_rate": max(bb_rate, 0.001),
        "hbp_rate": max(hbp_rate, 0.001),
        "single_rate_bip": single_rate_bip,
        "double_rate_bip": double_rate_bip,
        "triple_rate_bip": triple_rate_bip,
        "hr_rate_bip": hr_rate_bip,
        "go_rate_bip": go_rate_bip,
        "fo_rate_bip": fo_rate_bip,
    }


def _build_pitcher_splits(mlb_id: int, splits_data: dict, league: LeagueStats) -> dict | None:
    """Statcast splits 데이터에서 투수 platoon splits 구성."""
    vs_lhb = splits_data.get((mlb_id, "pitcher", "vs_LHB"))
    vs_rhb = splits_data.get((mlb_id, "pitcher", "vs_RHB"))

    if vs_lhb is None and vs_rhb is None:
        return None

    result = {}
    for split_name, data in [("vs_LHB", vs_lhb), ("vs_RHB", vs_rhb)]:
        if data is None:
            continue
        pa = int(data["pa"])
        if pa < 10:
            continue
        result[split_name] = _compute_pitcher_split_rates(data, league)

    return result if result else None


def _compute_pitcher_split_rates(data: dict, league: LeagueStats) -> dict:
    """단일 split 데이터에서 투수 rate 스탯 계산."""
    pa = int(data["pa"])
    k = int(data["strikeouts"])
    bb = int(data["walks"])
    ibb = int(data.get("ibb", 0))
    hbp = int(data["hbp"])
    hr = int(data["home_runs"])
    gb = int(data["ground_balls"])
    fb = int(data["fly_balls"])

    k_rate = k / pa if pa > 0 else league.k_rate
    bb_rate = (bb - ibb) / pa if pa > 0 else league.bb_rate
    hbp_rate = hbp / pa if pa > 0 else league.hbp_rate

    bip = pa - k - bb - ibb - hbp
    hr_rate_bip = hr / bip if bip > 0 else league.hr_rate_bip
    go_fo_ratio = gb / fb if fb > 0 else league.go_fo_ratio

    return {
        "pa": pa,
        "k_rate": max(k_rate, 0.001),
        "bb_rate": max(bb_rate, 0.001),
        "hbp_rate": max(hbp_rate, 0.001),
        "hr_rate_bip": max(hr_rate_bip, 0.001),
        "go_fo_ratio": max(go_fo_ratio, 0.1),
    }
