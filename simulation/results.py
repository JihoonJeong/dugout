"""경기별 시뮬레이션 결과 데이터 클래스."""

from __future__ import annotations

from dataclasses import dataclass, field

from data.schedule import GameRecord


@dataclass
class GameLevelResults:
    games: list[GameRecord]
    fallback_stats: dict[str, int]
    n_sims_per_game: int
    n_skipped: int = 0  # 선발 매핑 실패 등으로 스킵된 경기 수

    @property
    def n_valid(self) -> int:
        return len(self.games)

    @property
    def fallback_rate(self) -> float:
        total = self.n_valid * 2  # 양쪽 선발
        fallbacks = sum(self.fallback_stats.values())
        return fallbacks / total if total > 0 else 0.0
