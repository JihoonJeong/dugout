"""29개 상대팀 자동 관리 — 로테이션/라인업 고정."""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.models import PitcherStats, Team
from data.pipeline import DugoutData


@dataclass
class RotationState:
    """팀 선발 로테이션 상태."""
    starters: list[PitcherStats]
    current_idx: int = 0

    def next_starter(self) -> PitcherStats:
        starter = self.starters[self.current_idx]
        self.current_idx = (self.current_idx + 1) % len(self.starters)
        return starter


class AutoTeamManager:
    """29개 상대팀의 로테이션/라인업을 자동 관리.

    시즌 시작 시 각 팀의 투수진에서 상위 5명을 로테이션으로 설정.
    라인업은 data.teams의 고정 라인업 사용.
    """

    def __init__(self, data: DugoutData, user_team_id: str):
        self._data = data
        self._user_team_id = user_team_id
        self._rotations: dict[str, RotationState] = {}

        for team_id, team in data.teams.items():
            # 로테이션: starter + bullpen에서 상위 5명 선발
            # 기존 build_team에서 starter는 이미 GS 기준 1번 선발
            # 나머지 불펜에서 PA 기준 상위 4명을 추가 로테이션으로
            rotation = [team.starter]

            # 불펜에서 PA가 많은 순으로 4명 추가 (실제로는 선발 역할 투수)
            bp_sorted = sorted(team.bullpen, key=lambda p: p.pa_against, reverse=True)
            for p in bp_sorted[:4]:
                if p.player_id != team.starter.player_id:
                    rotation.append(p)
                if len(rotation) >= 5:
                    break

            # 5명 안 되면 있는 만큼
            self._rotations[team_id] = RotationState(starters=rotation)

    def get_team_for_game(self, team_id: str, as_home: bool = False) -> Team:
        """경기용 팀 객체 반환 (로테이션 반영)."""
        base_team = self._data.teams[team_id]
        rotation = self._rotations[team_id]
        starter = rotation.next_starter()

        # 불펜에서 선발 제외
        bullpen = [p for p in base_team.bullpen if p.player_id != starter.player_id]
        if not bullpen:
            bullpen = base_team.bullpen

        return Team(
            team_id=team_id,
            name=base_team.name,
            lineup=base_team.lineup,
            starter=starter,
            bullpen=bullpen,
        )

    def get_rotation(self, team_id: str) -> list[PitcherStats]:
        return self._rotations[team_id].starters

    def get_rotation_index(self, team_id: str) -> int:
        return self._rotations[team_id].current_idx
