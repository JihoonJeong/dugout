from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class BatterStats:
    player_id: str
    name: str
    hand: str  # "L", "R", "S" (switch)
    pa: int
    k_rate: float
    bb_rate: float
    hbp_rate: float
    # BIP 결과 (조건부 확률, 합 = 1.0)
    single_rate_bip: float
    double_rate_bip: float
    triple_rate_bip: float
    hr_rate_bip: float
    go_rate_bip: float
    fo_rate_bip: float
    # Platoon splits (Optional — 없으면 overall 사용)
    splits: Optional[dict] = None
    # splits = {
    #   "vs_LHP": {"pa": int, "k_rate": float, "bb_rate": float, "hbp_rate": float,
    #              "single_rate_bip": float, "double_rate_bip": float, ...},
    #   "vs_RHP": {"pa": int, "k_rate": float, "bb_rate": float, ...}
    # }


@dataclass
class PitcherStats:
    player_id: str
    name: str
    hand: str  # "L", "R"
    pa_against: int
    k_rate: float
    bb_rate: float
    hbp_rate: float
    hr_rate_bip: float
    go_fo_ratio: float
    # Platoon splits (Optional)
    splits: Optional[dict] = None
    # splits = {
    #   "vs_LHB": {"pa": int, "k_rate": float, "bb_rate": float, "hbp_rate": float,
    #              "hr_rate_bip": float, "go_fo_ratio": float},
    #   "vs_RHB": {"pa": int, "k_rate": float, "bb_rate": float, ...}
    # }


@dataclass
class LeagueStats:
    season: int
    k_rate: float
    bb_rate: float
    hbp_rate: float
    single_rate_bip: float
    double_rate_bip: float
    triple_rate_bip: float
    hr_rate_bip: float
    go_rate_bip: float
    fo_rate_bip: float
    go_fo_ratio: float


@dataclass
class ParkFactors:
    park_name: str
    pf_1b: float  # 100 = neutral
    pf_2b: float
    pf_3b: float
    pf_hr: float


@dataclass
class AtBatResult:
    event: str  # "K", "BB", "1B", "HR", etc.
    probabilities: dict[str, float]  # 전체 확률 분포


# ---------------------------------------------------------------------------
# Phase 0-CD: 게임 시뮬레이션 모델
# ---------------------------------------------------------------------------


@dataclass
class Runner:
    player_id: str
    name: str
    from_base: str  # 이 타석 시작 시 있던 베이스 ("1B", "2B", "3B")


@dataclass
class PitcherState:
    pitcher: PitcherStats
    pitch_count: int
    innings_pitched: float
    is_starter: bool


@dataclass
class PlayEvent:
    inning: int
    half: str
    batter: str  # player_id
    pitcher: str  # player_id
    event: str  # "K", "1B", "HR", "GO_DP", "FO_SF" 등
    runners_before: dict
    runners_after: dict
    runs_scored: int
    outs_before: int
    outs_after: int
    description: str


@dataclass
class GameState:
    inning: int
    half: str  # "top" | "bottom"
    outs: int
    runners: dict[str, Runner]
    score: dict[str, int]
    batting_order_idx: dict[str, int]
    current_pitcher: dict[str, PitcherState]
    game_over: bool
    play_log: list[PlayEvent]


@dataclass
class Team:
    team_id: str
    name: str
    lineup: list[BatterStats]  # 9명 타순 (index 0 = 1번 타자)
    starter: PitcherStats
    bullpen: list[PitcherStats]
    _reliever_idx: int = field(default=0, repr=False)

    def get_next_reliever(self) -> Optional[PitcherStats]:
        """다음 사용 가능한 불펜 투수 반환. 소진 시 None."""
        if self._reliever_idx >= len(self.bullpen):
            return None
        reliever = self.bullpen[self._reliever_idx]
        self._reliever_idx += 1
        return reliever

    def reset_bullpen(self) -> None:
        """불펜 인덱스 초기화 (새 게임 시작 시)."""
        self._reliever_idx = 0


@dataclass
class GameResult:
    score: dict[str, int]
    winner: str  # "away" | "home" | "tie"
    innings_played: int
    play_log: list[PlayEvent]
    hits: dict[str, int]
    runs_by_inning: dict[str, list[int]]
    total_pitches: dict[str, int]

    def box_score(self) -> str:
        """인간이 읽을 수 있는 박스 스코어 문자열."""
        away_runs = self.runs_by_inning["away"]
        home_runs = self.runs_by_inning["home"]
        n_innings = max(len(away_runs), len(home_runs))

        header = "         " + "".join(f"{i+1:>3}" for i in range(n_innings)) + "     R  H"
        away_line = "  Away   " + "".join(f"{r:>3}" for r in away_runs)
        home_line = "  Home   " + "".join(f"{r:>3}" for r in home_runs)

        # 9회말 미진행 시 'X' 표시
        if len(home_runs) < len(away_runs):
            home_line += "  X"

        away_line += f"  — {self.score['away']:>2} {self.hits['away']:>2}"
        home_line += f"  — {self.score['home']:>2} {self.hits['home']:>2}"

        return f"{header}\n{away_line}\n{home_line}"

    def summary(self) -> dict:
        return {
            "score": self.score,
            "winner": self.winner,
            "innings_played": self.innings_played,
            "hits": self.hits,
            "total_pitches": self.total_pitches,
        }


@dataclass
class SeriesResult:
    results: list[GameResult]

    @property
    def away_win_pct(self) -> float:
        wins = sum(1 for r in self.results if r.winner == "away")
        return wins / len(self.results)

    @property
    def home_win_pct(self) -> float:
        wins = sum(1 for r in self.results if r.winner == "home")
        return wins / len(self.results)

    @property
    def avg_total_runs(self) -> float:
        return float(np.mean([r.score["away"] + r.score["home"] for r in self.results]))

    @property
    def avg_away_runs(self) -> float:
        return float(np.mean([r.score["away"] for r in self.results]))

    @property
    def avg_home_runs(self) -> float:
        return float(np.mean([r.score["home"] for r in self.results]))

    def score_distribution(self, side: str) -> dict[int, float]:
        scores = [r.score[side] for r in self.results]
        counts = Counter(scores)
        return {k: v / len(scores) for k, v in sorted(counts.items())}

    def summary(self) -> dict:
        return {
            "n_simulations": len(self.results),
            "away_win_pct": self.away_win_pct,
            "home_win_pct": self.home_win_pct,
            "avg_away_runs": self.avg_away_runs,
            "avg_home_runs": self.avg_home_runs,
            "avg_total_runs": self.avg_total_runs,
            "extra_innings_pct": sum(
                1 for r in self.results if r.innings_played > 9
            )
            / len(self.results),
        }
