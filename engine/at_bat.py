"""타석 확률 모델 — Phase 0-B 핵심 구현.

투수-타자 매치업이 주어졌을 때, 해당 타석의 결과를 확률 분포로 산출한다.
Two-Stage Model: Stage 1 (Plate Discipline) → Stage 2 (Batted Ball Outcome).
"""

import numpy as np

from .constants import (
    FO_FLOOR,
    MAX_NON_BIP,
    PLATOON_MIN_PA,
    PROB_FLOOR,
    RATE_FLOOR,
    SMALL_SAMPLE_DIVISOR,
    SMALL_SAMPLE_PA,
    TOLERANCE,
)
from .models import AtBatResult, BatterStats, LeagueStats, ParkFactors, PitcherStats


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def calculate_matchup_probabilities(
    batter: BatterStats,
    pitcher: PitcherStats,
    league: LeagueStats,
    park: ParkFactors,
) -> dict[str, float]:
    """투수-타자 매치업의 이벤트별 확률 분포를 산출."""

    # === Platoon 처리 ===
    bat_stats = _resolve_batter_platoon(batter, pitcher.hand)
    pit_stats = _resolve_pitcher_platoon(pitcher, _effective_batter_hand(batter, pitcher.hand))

    # === Stage 1: Plate Discipline ===
    p_k = _log5(bat_stats["k_rate"], pit_stats["k_rate"], league.k_rate)
    p_bb = _log5(bat_stats["bb_rate"], pit_stats["bb_rate"], league.bb_rate)
    p_hbp = _log5(bat_stats["hbp_rate"], pit_stats["hbp_rate"], league.hbp_rate)

    # 정규화: K + BB + HBP가 MAX_NON_BIP을 초과하면 비율 유지하며 축소
    total_non_bip = p_k + p_bb + p_hbp
    if total_non_bip > MAX_NON_BIP:
        scale = MAX_NON_BIP / total_non_bip
        p_k *= scale
        p_bb *= scale
        p_hbp *= scale

    p_bip = 1.0 - p_k - p_bb - p_hbp

    # === Stage 2: Batted Ball Outcome ===
    base = {
        "1B": bat_stats["single_rate_bip"],
        "2B": bat_stats["double_rate_bip"],
        "3B": bat_stats["triple_rate_bip"],
        "HR": bat_stats["hr_rate_bip"],
        "GO": bat_stats["go_rate_bip"],
        "FO": bat_stats["fo_rate_bip"],
    }

    # 투수의 GB/FB 보정
    gb_fb_adj = pit_stats["go_fo_ratio"] / league.go_fo_ratio
    base["GO"] *= gb_fb_adj
    base["FO"] /= gb_fb_adj

    # 투수의 HR 보정
    hr_adj = pit_stats["hr_rate_bip"] / league.hr_rate_bip
    hr_delta = base["HR"] * (hr_adj - 1.0)
    base["HR"] += hr_delta
    base["FO"] -= hr_delta  # HR 증감은 FO에서 보상
    base["FO"] = max(base["FO"], FO_FLOOR)

    # Park Factor 보정
    base["1B"] *= park.pf_1b / 100
    base["2B"] *= park.pf_2b / 100
    base["3B"] *= park.pf_3b / 100
    base["HR"] *= park.pf_hr / 100

    # 음수 방지
    for key in base:
        if base[key] < PROB_FLOOR:
            base[key] = PROB_FLOOR

    # 정규화: BIP 내 확률 합 = 1.0
    bip_total = sum(base.values())
    for key in base:
        base[key] /= bip_total

    # === 최종 확률 ===
    result = {
        "K": p_k,
        "BB": p_bb,
        "HBP": p_hbp,
        "1B": p_bip * base["1B"],
        "2B": p_bip * base["2B"],
        "3B": p_bip * base["3B"],
        "HR": p_bip * base["HR"],
        "GO": p_bip * base["GO"],
        "FO": p_bip * base["FO"],
    }

    # 최종 검증
    total = sum(result.values())
    assert abs(total - 1.0) < TOLERANCE, f"확률 합이 1.0이 아닙니다: {total}"

    return result


def simulate_at_bat(
    batter: BatterStats,
    pitcher: PitcherStats,
    league: LeagueStats,
    park: ParkFactors,
    rng: np.random.Generator,
) -> AtBatResult:
    """단일 타석을 시뮬레이션하여 결과를 반환."""
    probs = calculate_matchup_probabilities(batter, pitcher, league, park)

    events = list(probs.keys())
    weights = list(probs.values())

    result_event = rng.choice(events, p=weights)
    return AtBatResult(event=result_event, probabilities=probs)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_BATTER_RATE_FIELDS = [
    "k_rate", "bb_rate", "hbp_rate",
    "single_rate_bip", "double_rate_bip", "triple_rate_bip",
    "hr_rate_bip", "go_rate_bip", "fo_rate_bip",
]

_PITCHER_RATE_FIELDS = [
    "k_rate", "bb_rate", "hbp_rate",
    "hr_rate_bip", "go_fo_ratio",
]


def _log5(p_bat: float, p_pit: float, p_lg: float) -> float:
    """Log5 확률 결합."""
    # 0이나 1에 의한 odds 계산 불가 방지
    p_bat = max(min(p_bat, 1 - RATE_FLOOR), RATE_FLOOR)
    p_pit = max(min(p_pit, 1 - RATE_FLOOR), RATE_FLOOR)
    p_lg = max(min(p_lg, 1 - RATE_FLOOR), RATE_FLOOR)

    odds_bat = p_bat / (1 - p_bat)
    odds_pit = p_pit / (1 - p_pit)
    odds_lg = p_lg / (1 - p_lg)

    odds_combined = odds_bat * odds_pit / odds_lg
    return odds_combined / (1 + odds_combined)


def _effective_batter_hand(batter: BatterStats, pitcher_hand: str) -> str:
    """스위치 히터의 실제 타석 결정."""
    if batter.hand == "S":
        # 스위치 히터: 상대 투수 반대 타석
        return "L" if pitcher_hand == "R" else "R"
    return batter.hand


def _resolve_batter_platoon(batter: BatterStats, pitcher_hand: str) -> dict:
    """타자의 좌우 분할 성적 적용 (소표본 보정 포함)."""
    overall = {field: getattr(batter, field) for field in _BATTER_RATE_FIELDS}

    # 극소 표본 회귀
    if batter.pa < SMALL_SAMPLE_PA:
        # 이 경우는 caller가 리그 평균을 넘겨줘야 하지만,
        # 현재 구조에서는 overall 성적 그대로 사용 (리그 평균 회귀는 데이터 로더에서 처리)
        return overall

    if batter.splits is None:
        return overall

    split_key = f"vs_{pitcher_hand}HP"  # "vs_LHP" or "vs_RHP"
    split = batter.splits.get(split_key)

    if split is None:
        return overall

    n = split.get("pa", 0)
    weight = min(n / PLATOON_MIN_PA, 1.0)

    blended = {}
    for field in _BATTER_RATE_FIELDS:
        split_val = split.get(field, overall[field])
        blended[field] = weight * split_val + (1 - weight) * overall[field]

    return blended


def _resolve_pitcher_platoon(pitcher: PitcherStats, batter_hand: str) -> dict:
    """투수의 좌우 분할 성적 적용 (소표본 보정 포함)."""
    overall = {field: getattr(pitcher, field) for field in _PITCHER_RATE_FIELDS}

    if pitcher.splits is None:
        return overall

    split_key = f"vs_{batter_hand}HB"  # "vs_LHB" or "vs_RHB"
    split = pitcher.splits.get(split_key)

    if split is None:
        return overall

    n = split.get("pa", 0)
    weight = min(n / PLATOON_MIN_PA, 1.0)

    blended = {}
    for field in _PITCHER_RATE_FIELDS:
        split_val = split.get(field, overall[field])
        blended[field] = weight * split_val + (1 - weight) * overall[field]

    return blended
