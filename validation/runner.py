"""ValidationRunner — L1~L4 검증 오케스트레이터."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from data.pipeline import DugoutData, DugoutDataPipeline
from .ground_truth import ActualResults, load_actual_results
from .l1_player import L1Result, run_l1
from .l2_team import L2Result, run_l2
from .l3_game import L3Result, run_l3
from .l4_season import L4Result, run_l4

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    season: int
    version: str
    timestamp: float
    l1: L1Result | None = None
    l2: L2Result | None = None
    l3: L3Result | None = None
    l4: L4Result | None = None
    elapsed_seconds: dict[str, float] = field(default_factory=dict)

    def summary(self) -> dict[str, dict[str, bool]]:
        """전체 pass/fail 요약."""
        result = {}
        if self.l1:
            result["L1"] = self.l1.passed()
        if self.l2:
            result["L2"] = self.l2.passed()
        if self.l3:
            result["L3"] = self.l3.passed()
        if self.l4:
            result["L4"] = self.l4.passed()
        return result

    def all_passed(self) -> bool:
        for level_results in self.summary().values():
            if not all(level_results.values()):
                return False
        return True

    def to_dict(self) -> dict:
        """직렬화용 dict 변환."""
        d: dict = {
            "season": self.season,
            "version": self.version,
            "timestamp": self.timestamp,
            "elapsed_seconds": self.elapsed_seconds,
            "summary": self.summary(),
        }
        if self.l1:
            d["l1"] = {
                "n_batters": self.l1.n_batters,
                "k_rmse": self.l1.k_rmse,
                "bb_rmse": self.l1.bb_rmse,
                "hr_rmse": self.l1.hr_rmse,
                "woba_rmse": self.l1.woba_rmse,
                "woba_corr": self.l1.woba_corr,
                "league_avg_restoration": self.l1.league_avg_restoration,
            }
        if self.l2:
            d["l2"] = {
                "n_teams": self.l2.n_teams,
                "runs_corr": self.l2.runs_corr,
                "runs_rmse": self.l2.runs_rmse,
                "mean_sim_runs": self.l2.mean_sim_runs,
                "mean_actual_runs": self.l2.mean_actual_runs,
                "scoring_bias": self.l2.scoring_bias,
            }
        if self.l3:
            d["l3"] = {
                "n_games": self.l3.n_games,
                "brier_score": self.l3.brier_score,
                "log_loss": self.l3.log_loss,
                "auc_roc": self.l3.auc_roc,
            }
        if self.l4:
            d["l4"] = {
                "n_teams": self.l4.n_teams,
                "wins_rmse": self.l4.wins_rmse,
                "wins_corr": self.l4.wins_corr,
                "playoff_correct": self.l4.playoff_correct,
                "playoff_total": self.l4.playoff_total,
                "pythag_wins_rmse": self.l4.pythag_wins_rmse,
                "sim_pythag_wins_rmse": self.l4.sim_pythag_wins_rmse,
                "sim_pythag_vs_direct_rmse": self.l4.sim_pythag_vs_direct_rmse,
            }
        return d


class ValidationRunner:
    """L1~L4 검증을 순차 실행하는 오케스트레이터."""

    def __init__(
        self,
        season: int = 2024,
        version: str = "v0.1",
        cache_dir: str = "cache/",
        output_dir: str = "output/validation/",
    ):
        self.season = season
        self.version = version
        self.cache_dir = cache_dir
        self.output_dir = Path(output_dir)

    def run(
        self,
        levels: list[str] | None = None,
        l3_max_games: int | None = 500,
        seed: int = 42,
    ) -> ValidationResult:
        """검증 실행.

        Args:
            levels: 실행할 레벨 (None이면 전부). e.g. ["L1", "L2"]
            l3_max_games: L3 경기 샘플 수 (None이면 전체)
            seed: 시뮬레이션 시드
        """
        if levels is None:
            levels = ["L1", "L2", "L3", "L4"]
        levels = [l.upper() for l in levels]

        result = ValidationResult(
            season=self.season,
            version=self.version,
            timestamp=time.time(),
        )

        # 데이터 로드
        t0 = time.time()
        logger.info("Loading data for season %d...", self.season)
        pipeline = DugoutDataPipeline(cache_dir=self.cache_dir, season=self.season)
        data = pipeline.load_all()
        actual = load_actual_results(self.season, cache_dir=self.cache_dir)
        result.elapsed_seconds["data_load"] = time.time() - t0
        logger.info("Data loaded in %.1fs", result.elapsed_seconds["data_load"])

        # L1: 선수 정확도
        if "L1" in levels:
            t0 = time.time()
            logger.info("Running L1 (player accuracy)...")
            result.l1 = run_l1(data.all_batters, data.league, actual, teams=data.teams)
            result.elapsed_seconds["L1"] = time.time() - t0

        # L2: 팀 득점
        if "L2" in levels:
            t0 = time.time()
            logger.info("Running L2 (team scoring)...")
            result.l2 = run_l2(data.teams, data.league, actual, seed=seed)
            result.elapsed_seconds["L2"] = time.time() - t0

        # L3: 경기 예측
        if "L3" in levels:
            t0 = time.time()
            logger.info("Running L3 (game prediction)...")
            result.l3 = run_l3(
                data.teams, data.parks, data.league, actual,
                max_games=l3_max_games, seed=seed,
            )
            result.elapsed_seconds["L3"] = time.time() - t0

        # L4: 시즌 예측
        if "L4" in levels:
            t0 = time.time()
            logger.info("Running L4 (season prediction)...")
            result.l4 = run_l4(
                data.teams, data.parks, data.league, actual, seed=seed,
            )
            result.elapsed_seconds["L4"] = time.time() - t0

        total = sum(result.elapsed_seconds.values())
        logger.info("Validation complete in %.1fs", total)
        result.elapsed_seconds["total"] = total

        # 결과 저장
        self._save_result(result)
        self._update_history(result)

        return result

    def _save_result(self, result: ValidationResult) -> None:
        """검증 결과를 JSON으로 저장."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / f"result_{self.version}_{self.season}.json"
        with open(path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        logger.info("Saved result to %s", path)

    def _update_history(self, result: ValidationResult) -> None:
        """metrics_history.json에 결과 추가."""
        history_path = self.output_dir / "metrics_history.json"
        history: list[dict] = []
        if history_path.exists():
            with open(history_path) as f:
                history = json.load(f)

        history.append(result.to_dict())

        with open(history_path, "w") as f:
            json.dump(history, f, indent=2)
