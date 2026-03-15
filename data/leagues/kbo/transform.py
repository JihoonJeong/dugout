"""KBO 스탯 변환 — 원시 스탯 → 엔진용 BatterStats/PitcherStats.

MLB transform.py와 동일한 수식을 사용합니다.
GO/FO 데이터가 없으므로 리그 평균으로 추정합니다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from engine.models import BatterStats, PitcherStats, LeagueStats

from .extract import KBOBatterRaw, KBOPitcherRaw

logger = logging.getLogger(__name__)

# KBO 리그 평균 추정치 (MLB 대비 약간 다른 환경)
# GO/FO 데이터가 없으므로 MLB 평균과 KBO 특성을 기반으로 추정
_DEFAULT_GB_SHARE = 0.44  # Ground ball share of batted balls


def calculate_kbo_league_stats(
    batters: list[KBOBatterRaw],
    season: int = 2025,
) -> LeagueStats:
    """KBO 전체 타자 데이터로 리그 평균 스탯 계산."""
    total_pa = sum(b.pa for b in batters if b.pa > 0)
    total_k = sum(b.strikeouts for b in batters)
    total_bb = sum(b.walks for b in batters)
    total_hbp = sum(b.hbp for b in batters)
    total_h = sum(b.hits for b in batters)
    total_2b = sum(b.doubles for b in batters)
    total_3b = sum(b.triples for b in batters)
    total_hr = sum(b.home_runs for b in batters)
    total_1b = total_h - total_2b - total_3b - total_hr

    if total_pa == 0:
        raise ValueError("No batter PA data for league stats calculation")

    total_bip = total_pa - total_k - total_bb - total_hbp
    if total_bip <= 0:
        raise ValueError("Invalid BIP calculation")

    total_outs_bip = total_bip - total_1b - total_2b - total_3b - total_hr
    go_count = round(total_outs_bip * _DEFAULT_GB_SHARE)
    fo_count = total_outs_bip - go_count

    return LeagueStats(
        season=season,
        k_rate=total_k / total_pa,
        bb_rate=total_bb / total_pa,
        hbp_rate=total_hbp / total_pa,
        single_rate_bip=total_1b / total_bip,
        double_rate_bip=total_2b / total_bip,
        triple_rate_bip=total_3b / total_bip,
        hr_rate_bip=total_hr / total_bip,
        go_rate_bip=go_count / total_bip,
        fo_rate_bip=fo_count / total_bip,
        go_fo_ratio=go_count / fo_count if fo_count > 0 else 1.0,
    )


def convert_batter(
    raw: KBOBatterRaw,
    league: LeagueStats,
) -> BatterStats | None:
    """KBO 타자 원시 스탯 → 엔진용 BatterStats."""
    if raw.pa < 30:
        return None

    k_rate = max(raw.strikeouts / raw.pa, 0.001)
    bb_rate = max(raw.walks / raw.pa, 0.001)
    hbp_rate = max(raw.hbp / raw.pa, 0.001)

    bip = raw.pa - raw.strikeouts - raw.walks - raw.hbp
    if bip <= 0:
        return None

    singles = max(raw.hits - raw.doubles - raw.triples - raw.home_runs, 0)

    single_rate_bip = singles / bip
    double_rate_bip = raw.doubles / bip
    triple_rate_bip = raw.triples / bip
    hr_rate_bip = raw.home_runs / bip

    # GO/FO: no data available, use league average split
    outs_bip = bip - singles - raw.doubles - raw.triples - raw.home_runs
    if outs_bip > 0:
        go_count = round(outs_bip * _DEFAULT_GB_SHARE)
        fo_count = outs_bip - go_count
        go_rate_bip = go_count / bip
        fo_rate_bip = fo_count / bip
    else:
        go_rate_bip = league.go_rate_bip
        fo_rate_bip = league.fo_rate_bip

    # Normalize BIP rates to sum to 1.0
    bip_total = (single_rate_bip + double_rate_bip + triple_rate_bip +
                 hr_rate_bip + go_rate_bip + fo_rate_bip)
    if bip_total > 0 and abs(bip_total - 1.0) > 0.001:
        single_rate_bip /= bip_total
        double_rate_bip /= bip_total
        triple_rate_bip /= bip_total
        hr_rate_bip /= bip_total
        go_rate_bip /= bip_total
        fo_rate_bip /= bip_total

    return BatterStats(
        player_id=f"kbo_{raw.name}_{raw.team_id}",
        name=raw.name,
        hand="R",  # KBO doesn't provide handedness in basic stats
        pa=raw.pa,
        k_rate=k_rate,
        bb_rate=bb_rate,
        hbp_rate=hbp_rate,
        single_rate_bip=single_rate_bip,
        double_rate_bip=double_rate_bip,
        triple_rate_bip=triple_rate_bip,
        hr_rate_bip=hr_rate_bip,
        go_rate_bip=go_rate_bip,
        fo_rate_bip=fo_rate_bip,
    )


def convert_pitcher(
    raw: KBOPitcherRaw,
    league: LeagueStats,
) -> PitcherStats | None:
    """KBO 투수 원시 스탯 → 엔진용 PitcherStats."""
    if raw.tbf < 30:
        return None

    k_rate = max(raw.strikeouts / raw.tbf, 0.001)
    bb_rate = max(raw.walks / raw.tbf, 0.001)
    hbp_rate = max(raw.hbp / raw.tbf, 0.001)

    bip = raw.tbf - raw.strikeouts - raw.walks - raw.hbp
    if bip <= 0:
        hr_rate_bip = league.hr_rate_bip
    else:
        hr_rate_bip = max(raw.home_runs / bip, 0.001)

    # GO/FO ratio: no data, use league average
    go_fo_ratio = max(league.go_fo_ratio, 0.1)

    # Determine role
    role = "SP" if raw.games > 0 and raw.ip / max(raw.games, 1) >= 3.0 else "RP"

    return PitcherStats(
        player_id=f"kbo_{raw.name}_{raw.team_id}",
        name=raw.name,
        hand="R",  # default
        pa_against=raw.tbf,
        k_rate=k_rate,
        bb_rate=bb_rate,
        hbp_rate=hbp_rate,
        hr_rate_bip=hr_rate_bip,
        go_fo_ratio=go_fo_ratio,
    ), role
