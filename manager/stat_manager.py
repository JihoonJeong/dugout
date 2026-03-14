"""StatManager — 규칙 기반 AI 감독."""

from __future__ import annotations

from .base import (
    DecisionEvent,
    GameSituation,
    Manager,
    ManagerDecision,
    NO_ACTION,
)
from .leverage import is_save_situation
from .philosophy import ManagerPhilosophy, NEUTRAL


class StatManager(Manager):
    """통계 규칙 기반 감독.

    투수 교체와 고의사구를 ManagerPhilosophy에 따라 결정.
    """

    def __init__(self, philosophy: ManagerPhilosophy | None = None):
        self._philosophy = philosophy or NEUTRAL
        self.decision_log: list[DecisionEvent] = []

    @property
    def name(self) -> str:
        return f"StatManager({self._philosophy.name})"

    @property
    def philosophy(self) -> ManagerPhilosophy:
        return self._philosophy

    def decide(self, sit: GameSituation) -> ManagerDecision:
        """상황을 분석하고 결정을 반환."""
        # 1. 투수 교체 판단
        change = self._check_pitching_change(sit)
        if change is not None:
            self._log(sit, change)
            return change

        # 2. 고의사구 판단
        ibb = self._check_intentional_walk(sit)
        if ibb is not None:
            self._log(sit, ibb)
            return ibb

        return NO_ACTION

    def _check_pitching_change(self, sit: GameSituation) -> ManagerDecision | None:
        """투수 교체 여부 판단."""
        phil = self._philosophy

        if sit.bullpen_available <= 0:
            return None

        should_change = False
        reason_parts = []

        if sit.pitcher_is_starter:
            # 선발 교체 기준
            pitch_limit = phil.starter_pitch_limit
            inning_limit = phil.starter_inning_limit

            # 레버리지에 따른 동적 기준 조정
            if sit.leverage_index >= 2.0 and phil.leverage_sensitivity > 0.5:
                pitch_limit = int(pitch_limit * 0.9)
                inning_limit *= 0.85

            if sit.pitcher_pitch_count >= pitch_limit:
                should_change = True
                reason_parts.append(f"pitch count {sit.pitcher_pitch_count} >= {pitch_limit}")

            if sit.pitcher_innings >= inning_limit:
                should_change = True
                reason_parts.append(f"innings {sit.pitcher_innings:.1f} >= {inning_limit:.1f}")

        else:
            # 릴리버 교체 기준
            if sit.pitcher_innings >= phil.reliever_inning_limit:
                should_change = True
                reason_parts.append(
                    f"reliever innings {sit.pitcher_innings:.1f} >= {phil.reliever_inning_limit:.1f}"
                )

        if should_change:
            return ManagerDecision(
                action="pitching_change",
                reason="; ".join(reason_parts),
            )
        return None

    def _check_intentional_walk(self, sit: GameSituation) -> ManagerDecision | None:
        """고의사구 여부 판단."""
        phil = self._philosophy

        if phil.ibb_aggression <= 0:
            return None

        if sit.leverage_index < phil.ibb_leverage_threshold:
            return None

        # 1루가 비어야 고의사구 의미가 있음 (포스 플레이 만들기)
        if "1B" in sit.runners:
            return None

        # 주자가 득점권에 있어야 함 (2루 or 3루)
        has_scoring_pos = "2B" in sit.runners or "3B" in sit.runners
        if not has_scoring_pos:
            return None

        # 2아웃이 아니어야 함 (2아웃이면 후속 타자의 아웃 하나로 끝)
        # → 사실 2아웃 만루 포스가 오히려 유리할 수 있음. 양쪽 허용.

        # 아웃 < 2이고, 다음 타자가 더 약한 경우 IBB 발동
        # V1 단순화: aggression 확률로 결정
        # 높은 레버리지 + 높은 aggression → IBB
        ibb_score = phil.ibb_aggression * (sit.leverage_index / 3.0)
        if ibb_score < 0.4:
            return None

        return ManagerDecision(
            action="intentional_walk",
            reason=f"IBB: LI={sit.leverage_index:.1f}, scoring pos, 1B open",
            details={"walked_batter_id": sit.batter_id, "walked_batter_name": sit.batter_name},
        )

    def _log(self, sit: GameSituation, decision: ManagerDecision) -> None:
        summary = (
            f"{sit.inning}{'T' if sit.half == 'top' else 'B'} "
            f"{sit.outs}out "
            f"R:{','.join(sit.runners.keys()) or '-'} "
            f"Score:{sit.score['away']}-{sit.score['home']} "
            f"P:{sit.pitcher_name}({sit.pitcher_pitch_count}p)"
        )
        self.decision_log.append(DecisionEvent(
            inning=sit.inning,
            half=sit.half,
            outs=sit.outs,
            situation_summary=summary,
            decision=decision,
            leverage_index=sit.leverage_index,
        ))
