"""레버리지 인덱스 및 세이브 상황 계산."""

from __future__ import annotations


def calculate_leverage(
    inning: int,
    half: str,
    outs: int,
    runners: dict,
    score_diff: int,
) -> float:
    """간이 레버리지 인덱스 계산.

    정밀한 LI는 RE24 매트릭스가 필요하지만, V1에서는
    상황 기반 근사치를 사용.

    Returns:
        leverage index (1.0 = average, >2.0 = high leverage)
    """
    base_li = 1.0

    # 이닝 보정: 후반일수록 레버리지 증가
    if inning >= 9:
        base_li *= 1.8
    elif inning >= 7:
        base_li *= 1.4
    elif inning >= 5:
        base_li *= 1.1

    # 점수차 보정: 접전일수록 레버리지 증가
    abs_diff = abs(score_diff)
    if abs_diff == 0:
        base_li *= 1.5
    elif abs_diff == 1:
        base_li *= 1.3
    elif abs_diff == 2:
        base_li *= 1.1
    elif abs_diff >= 5:
        base_li *= 0.5

    # 주자 상황: 득점권에 주자가 있으면 증가
    n_runners = len(runners)
    if n_runners == 3:
        base_li *= 1.6  # 만루
    elif n_runners == 2:
        base_li *= 1.3
    elif n_runners == 1:
        if "3B" in runners:
            base_li *= 1.3
        elif "2B" in runners:
            base_li *= 1.2
        else:
            base_li *= 1.05

    # 아웃 보정: 2아웃이면 증가 (기회가 줄어드는 만큼)
    if outs == 2:
        base_li *= 1.2
    elif outs == 0:
        base_li *= 0.9

    return round(base_li, 2)


def is_save_situation(
    inning: int,
    half: str,
    score_diff: int,
    pitching_side: str,
) -> bool:
    """세이브 상황 판단.

    pitching_side 기준으로 리드하고 있는 상황에서 후반 이닝.
    score_diff > 0: pitching_side가 리드.
    """
    if inning < 7:
        return False
    if score_diff <= 0:
        return False
    return score_diff <= 3
