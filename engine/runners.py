"""주자 진루 모델.

타석 결과에 따라 주자 이동을 해결한다.
"""

import numpy as np

from data.runner_tables import (
    DOUBLE_ADVANCE,
    DP_PROBABILITY,
    DP_RUNNER_3B_SCORES,
    FO_TAGUP,
    GO_ADVANCE,
    GO_ADVANCE_3B_2_OUTS,
    GO_ADVANCE_3B_LESS_THAN_2_OUTS,
    SF_PROBABILITY,
    SINGLE_ADVANCE,
)
from .models import Runner


def resolve_play(
    event: str,
    runners: dict[str, Runner],
    outs: int,
    batter_id: str,
    batter_name: str,
    rng: np.random.Generator,
) -> tuple[dict[str, Runner], int, int]:
    """타석 결과에 따라 주자 이동, 득점, 추가 아웃을 반환.

    Returns:
        (runners_after, runs_scored, outs_added)
    """
    if event == "HR":
        return _resolve_hr(runners)
    elif event == "3B":
        return _resolve_triple(runners, batter_id, batter_name)
    elif event in ("BB", "HBP"):
        return _resolve_walk(runners, batter_id, batter_name)
    elif event == "K":
        return dict(runners), 0, 1
    elif event == "1B":
        return _resolve_hit(runners, batter_id, batter_name, SINGLE_ADVANCE, "1B", rng)
    elif event == "2B":
        return _resolve_hit(runners, batter_id, batter_name, DOUBLE_ADVANCE, "2B", rng)
    elif event == "GO":
        return _resolve_go(runners, outs, rng)
    elif event == "FO":
        return _resolve_fo(runners, outs, rng)
    else:
        raise ValueError(f"Unknown event: {event}")


def _resolve_hr(runners: dict[str, Runner]) -> tuple[dict[str, Runner], int, int]:
    runs = len(runners) + 1  # 모든 주자 + 타자
    return {}, runs, 0


def _resolve_triple(
    runners: dict[str, Runner], batter_id: str, batter_name: str
) -> tuple[dict[str, Runner], int, int]:
    runs = len(runners)
    after = {"3B": Runner(player_id=batter_id, name=batter_name, from_base="3B")}
    return after, runs, 0


def _resolve_walk(
    runners: dict[str, Runner], batter_id: str, batter_name: str
) -> tuple[dict[str, Runner], int, int]:
    """포스 진루만 발생."""
    after = {}
    runs = 0

    # 포스 체인: 1루부터 연쇄적으로 밀어냄
    has_1b = "1B" in runners
    has_2b = "2B" in runners
    has_3b = "3B" in runners

    if has_3b and has_2b and has_1b:
        # 만루 → 밀어내기
        runs = 1
    if has_3b and not (has_2b and has_1b):
        # 3루 주자는 포스가 아니면 잔류
        after["3B"] = runners["3B"]
    if has_2b and has_1b:
        after["3B"] = runners["2B"]
    elif has_2b:
        after["2B"] = runners["2B"]
    if has_1b:
        after["2B"] = runners["1B"]

    after["1B"] = Runner(player_id=batter_id, name=batter_name, from_base="1B")
    return after, runs, 0


def _resolve_hit(
    runners: dict[str, Runner],
    batter_id: str,
    batter_name: str,
    advance_table: dict,
    batter_dest: str,
    rng: np.random.Generator,
) -> tuple[dict[str, Runner], int, int]:
    """싱글/더블 시 확률적 진루."""
    after = {}
    runs = 0
    occupied = set()

    # 3루 → 2루 → 1루 역순 처리
    for base in ["3B", "2B", "1B"]:
        if base not in runners:
            continue
        table = advance_table.get(base)
        if table is None:
            # 테이블에 없으면 잔류
            after[base] = runners[base]
            occupied.add(base)
            continue

        dest = _sample_destination(table, rng)

        # 점유 충돌 방지: 앞 베이스가 차 있으면 한 단계 앞으로
        if dest != "HOME" and dest in occupied:
            dest = _next_base(dest)
            if dest is None:
                dest = "HOME"

        if dest == "HOME":
            runs += 1
        else:
            after[dest] = runners[base]
            occupied.add(dest)

    # 타자 배치
    if batter_dest in occupied:
        batter_dest = _next_base(batter_dest)
    after[batter_dest] = Runner(
        player_id=batter_id, name=batter_name, from_base=batter_dest
    )

    return after, runs, 0


def _resolve_go(
    runners: dict[str, Runner], outs: int, rng: np.random.Generator
) -> tuple[dict[str, Runner], int, int]:
    """땅볼 아웃 (DP 판정 포함)."""
    has_force = "1B" in runners
    dp_eligible = outs < 2 and has_force

    if dp_eligible and rng.random() < DP_PROBABILITY:
        return _resolve_go_dp(runners, rng)

    # 일반 GO
    after = {}
    runs = 0

    for base in ["3B", "2B", "1B"]:
        if base not in runners:
            continue
        if base == "3B":
            table = GO_ADVANCE_3B_LESS_THAN_2_OUTS if outs < 2 else GO_ADVANCE_3B_2_OUTS
        else:
            table = GO_ADVANCE.get(base)
            if table is None:
                after[base] = runners[base]
                continue

        dest = _sample_destination(table, rng)
        if dest == "HOME":
            runs += 1
        else:
            after[dest] = runners[base]

    return after, runs, 1  # 타자 아웃


def _resolve_go_dp(
    runners: dict[str, Runner], rng: np.random.Generator
) -> tuple[dict[str, Runner], int, int]:
    """더블플레이 처리."""
    after = {}
    runs = 0

    # 1루 주자 제거 (2루 포스아웃)
    remaining = {k: v for k, v in runners.items() if k != "1B"}

    for base in ["3B", "2B"]:
        if base not in remaining:
            continue
        if base == "3B":
            if rng.random() < DP_RUNNER_3B_SCORES:
                runs += 1
            else:
                after["3B"] = remaining["3B"]
        elif base == "2B":
            after["3B"] = remaining["2B"]

    return after, runs, 2  # 타자 + 포스 = 2아웃


def _resolve_fo(
    runners: dict[str, Runner], outs: int, rng: np.random.Generator
) -> tuple[dict[str, Runner], int, int]:
    """뜬공 아웃 (희생플라이 판정 포함)."""
    after = {}
    runs = 0

    has_third = "3B" in runners
    sf_eligible = outs < 2 and has_third

    if sf_eligible and rng.random() < SF_PROBABILITY:
        # 희생플라이 — 3루 주자 득점
        runs += 1
        # 나머지 주자 태그업
        for base in ["2B", "1B"]:
            if base in runners:
                dest = _sample_destination(FO_TAGUP[base], rng)
                after[dest] = runners[base]
    else:
        # 일반 FO
        if outs < 2:
            # 3루 주자 잔류 (태그업 실패)
            if has_third:
                after["3B"] = runners["3B"]
            # 나머지 태그업 시도
            for base in ["2B", "1B"]:
                if base in runners:
                    dest = _sample_destination(FO_TAGUP[base], rng)
                    after[dest] = runners[base]
        else:
            # 2아웃 FO: 이닝 종료이므로 주자 이동 무의미
            after = dict(runners)

    return after, runs, 1  # 타자 아웃


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_ORDER = ["1B", "2B", "3B", "HOME"]


def _sample_destination(table: dict[str, float], rng: np.random.Generator) -> str:
    """확률 테이블에서 목적지를 샘플링."""
    destinations = list(table.keys())
    probs = list(table.values())
    return rng.choice(destinations, p=probs)


def _next_base(base: str) -> str | None:
    """한 단계 앞 베이스 반환."""
    idx = _BASE_ORDER.index(base)
    if idx + 1 < len(_BASE_ORDER):
        return _BASE_ORDER[idx + 1]
    return None
