"""DailyPredictor — 엔진 기반 경기 예측.

MLB/KBO/NPB 멀티리그 지원.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Optional

import numpy as np

from data.constants import TEAM_MAPPING
from data.extract import fetch_id_mapping
from data.game_team_builder import build_game_team, build_mlb_to_fg_map, resolve_starter
from data.pipeline import DugoutData
from engine.models import ParkFactors, PitcherStats, Team
from engine.monte_carlo import simulate_series
from engine.game import simulate_game
from simulation.shrinkage import shrink_probability

from .pipeline import DailyGame

logger = logging.getLogger(__name__)

# 최적 파라미터 (Phase 1-A 캘리브레이션 결과)
DEFAULT_ALPHA = 0.35  # team_base vs game_starter 블렌딩
DEFAULT_SHRINK = 0.60  # 로지스틱 수축


@dataclass
class GamePrediction:
    """단일 경기 예측 결과."""
    game_id: int | str
    game_date: str
    away_team_id: str
    home_team_id: str
    away_starter_name: str
    home_starter_name: str
    game_time: str
    venue: str

    # Quick Sim (1회)
    quick_away_score: int = 0
    quick_home_score: int = 0
    quick_winner: str = ""
    quick_innings: int = 9

    # Monte Carlo (N회)
    mc_away_win_pct: float = 0.5
    mc_home_win_pct: float = 0.5
    mc_avg_away_runs: float = 0.0
    mc_avg_home_runs: float = 0.0
    mc_avg_total_runs: float = 0.0
    mc_n_sims: int = 0

    # 보정된 최종 확률 (블렌딩 + 수축)
    final_away_win_pct: float = 0.5
    final_home_win_pct: float = 0.5

    # 선발 해결 정보
    away_starter_fallback: Optional[str] = None
    home_starter_fallback: Optional[str] = None

    # 매치업 요약
    matchup_summary: str = ""


class DailyPredictor:
    """각 경기에 대해 엔진 시뮬레이션 기반 예측을 생성."""

    def __init__(
        self,
        data: DugoutData,
        alpha: float = DEFAULT_ALPHA,
        shrink: float = DEFAULT_SHRINK,
        cache_dir: str = "cache/",
    ):
        self._data = data
        self._alpha = alpha
        self._shrink = shrink

        # ID 매핑 로드
        id_mapping = fetch_id_mapping(cache_dir=cache_dir)
        self._mlb_to_fg = build_mlb_to_fg_map(data, id_mapping)
        logger.info("DailyPredictor ready: %d pitcher mappings", len(self._mlb_to_fg))

    def predict_game(
        self,
        game: DailyGame,
        n_sims: int = 1000,
        seed: int | None = None,
    ) -> GamePrediction:
        """단일 경기 예측."""
        if seed is None:
            seed = game.game_id % 1_000_000

        rng = np.random.default_rng(seed)

        # 선발투수 해결
        away_starter, fb_a = resolve_starter(
            game.away_starter_mlb_id, game.away_starter_name,
            game.away_team_id, self._data, self._mlb_to_fg,
        )
        home_starter, fb_h = resolve_starter(
            game.home_starter_mlb_id, game.home_starter_name,
            game.home_team_id, self._data, self._mlb_to_fg,
        )

        # 팀 구성
        away_team = build_game_team(game.away_team_id, away_starter, self._data)
        home_team = build_game_team(game.home_team_id, home_starter, self._data)

        park_name = TEAM_MAPPING[game.home_team_id]["park"]
        park = self._data.parks.get(park_name)
        if park is None:
            park = ParkFactors(park_name=park_name, pf_1b=100, pf_2b=100, pf_3b=100, pf_hr=100)

        # Quick Sim (1회)
        away_team.reset_bullpen()
        home_team.reset_bullpen()
        quick_result = simulate_game(away_team, home_team, park, self._data.league, rng)

        # Monte Carlo (N회)
        mc_series = simulate_series(
            away_team, home_team, park, self._data.league,
            n_simulations=n_sims,
            seed=int(rng.integers(1_000_000_000)),
        )

        # 팀 기본 승률 (고정 선발 기준 — Phase 0 proxy)
        base_away = build_game_team(
            game.away_team_id,
            self._data.teams[game.away_team_id].starter,
            self._data,
        )
        base_home = build_game_team(
            game.home_team_id,
            self._data.teams[game.home_team_id].starter,
            self._data,
        )
        base_series = simulate_series(
            base_away, base_home, park, self._data.league,
            n_simulations=200,
            seed=int(rng.integers(1_000_000_000)),
        )

        # 블렌딩: alpha × team_base + (1-alpha) × game_starter
        team_base_pct = base_series.away_win_pct
        game_starter_pct = mc_series.away_win_pct
        blended = self._alpha * team_base_pct + (1 - self._alpha) * game_starter_pct

        # 수축
        final_away = shrink_probability(blended, self._shrink)
        final_home = 1 - final_away

        # 매치업 요약
        summary = self._build_matchup_summary(
            game, away_starter, home_starter,
            mc_series.away_win_pct, mc_series.avg_away_runs, mc_series.avg_home_runs,
        )

        return GamePrediction(
            game_id=game.game_id,
            game_date=game.game_date,
            away_team_id=game.away_team_id,
            home_team_id=game.home_team_id,
            away_starter_name=away_starter.name,
            home_starter_name=home_starter.name,
            game_time=game.game_time,
            venue=game.venue,
            quick_away_score=quick_result.score["away"],
            quick_home_score=quick_result.score["home"],
            quick_winner=quick_result.winner,
            quick_innings=quick_result.innings_played,
            mc_away_win_pct=mc_series.away_win_pct,
            mc_home_win_pct=mc_series.home_win_pct,
            mc_avg_away_runs=mc_series.avg_away_runs,
            mc_avg_home_runs=mc_series.avg_home_runs,
            mc_avg_total_runs=mc_series.avg_total_runs,
            mc_n_sims=n_sims,
            final_away_win_pct=final_away,
            final_home_win_pct=final_home,
            away_starter_fallback=fb_a,
            home_starter_fallback=fb_h,
            matchup_summary=summary,
        )

    def predict_all(
        self,
        games: list[DailyGame],
        n_sims: int = 1000,
    ) -> list[GamePrediction]:
        """오늘의 모든 경기에 대해 예측 생성."""
        predictions = []
        t0 = time.time()

        for i, game in enumerate(games):
            if game.away_team_id not in self._data.teams:
                logger.warning("Unknown team: %s, skipping game %d", game.away_team_id, game.game_id)
                continue
            if game.home_team_id not in self._data.teams:
                logger.warning("Unknown team: %s, skipping game %d", game.home_team_id, game.game_id)
                continue

            pred = self.predict_game(game, n_sims=n_sims)
            predictions.append(pred)

            if (i + 1) % 5 == 0:
                elapsed = time.time() - t0
                logger.info("  %d/%d games predicted (%.1fs)", i + 1, len(games), elapsed)

        elapsed = time.time() - t0
        logger.info(
            "All predictions complete: %d games in %.1fs",
            len(predictions), elapsed,
        )
        return predictions

    def _build_matchup_summary(
        self,
        game: DailyGame,
        away_starter,
        home_starter,
        away_win_pct: float,
        avg_away_runs: float,
        avg_home_runs: float,
    ) -> str:
        """매치업 요약 텍스트 생성."""
        fav = game.away_team_id if away_win_pct > 0.5 else game.home_team_id
        fav_pct = max(away_win_pct, 1 - away_win_pct)

        parts = [
            f"{game.away_team_id} ({away_starter.name}) @ {game.home_team_id} ({home_starter.name})",
            f"Favored: {fav} ({fav_pct:.1%})",
            f"Projected: {avg_away_runs:.1f}-{avg_home_runs:.1f}",
        ]

        # 투수 핵심 스탯
        parts.append(
            f"Away SP: K%={away_starter.k_rate:.1%}, BB%={away_starter.bb_rate:.1%}"
        )
        parts.append(
            f"Home SP: K%={home_starter.k_rate:.1%}, BB%={home_starter.bb_rate:.1%}"
        )

        return " | ".join(parts)


# ── Multi-League Predictor ──────────────────────────────


def _resolve_starter_by_name(
    name: str,
    team_id: str,
    data: DugoutData,
) -> tuple[PitcherStats, Optional[str]]:
    """KBO/NPB용 선발투수 해결 — 이름 매칭만 사용."""
    if not name or name == "TBD":
        # 팀 기본 선발 사용
        if team_id in data.teams:
            return data.teams[team_id].starter, "team_default"
        return _league_avg_pitcher(data), "league_avg"

    # 1. Exact match (team-specific player_id pattern)
    for p in data.all_pitchers.values():
        if p.name == name:
            return p, None

    # 2. Fuzzy match
    best_score = 0.0
    best_match = None
    name_lower = name.lower()
    for p in data.all_pitchers.values():
        score = SequenceMatcher(None, name_lower, p.name.lower()).ratio()
        if score > best_score:
            best_score = score
            best_match = p
    if best_score >= 0.80 and best_match is not None:
        return best_match, "fuzzy"

    # 3. Team average
    if team_id in data.teams:
        team = data.teams[team_id]
        team_pitchers = [team.starter] + team.bullpen
        total_pa = sum(p.pa_against for p in team_pitchers)
        if total_pa > 0:
            avg = PitcherStats(
                player_id=f"avg_{team_id}", name="Team Average", hand="R",
                pa_against=total_pa,
                k_rate=sum(p.k_rate * p.pa_against for p in team_pitchers) / total_pa,
                bb_rate=sum(p.bb_rate * p.pa_against for p in team_pitchers) / total_pa,
                hbp_rate=sum(p.hbp_rate * p.pa_against for p in team_pitchers) / total_pa,
                hr_rate_bip=sum(p.hr_rate_bip * p.pa_against for p in team_pitchers) / total_pa,
                go_fo_ratio=sum(p.go_fo_ratio * p.pa_against for p in team_pitchers) / total_pa,
            )
            return avg, "team_avg"

    return _league_avg_pitcher(data), "league_avg"


def _league_avg_pitcher(data: DugoutData) -> PitcherStats:
    """리그 평균 투수 스탯 생성."""
    return PitcherStats(
        player_id="lg_avg", name="League Average", hand="R",
        pa_against=10000,
        k_rate=data.league.k_rate, bb_rate=data.league.bb_rate,
        hbp_rate=data.league.hbp_rate,
        hr_rate_bip=data.league.hr_rate_bip, go_fo_ratio=data.league.go_fo_ratio,
    )


def _build_game_team_generic(
    team_id: str,
    starter: PitcherStats,
    data: DugoutData,
) -> Team:
    """리그 불문 팀 구성 — DugoutData에서 팀 정보를 가져와 선발을 교체."""
    base_team = data.teams[team_id]
    bullpen = [p for p in base_team.bullpen if p.player_id != starter.player_id]
    return Team(
        team_id=team_id,
        name=base_team.name,
        lineup=base_team.lineup,
        starter=starter,
        bullpen=bullpen if bullpen else base_team.bullpen,
    )


class MultiLeaguePredictor:
    """MLB/KBO/NPB 멀티리그 예측기.

    각 리그의 DugoutData를 보유하고 game.league_id에 따라 라우팅합니다.
    """

    def __init__(
        self,
        mlb_data: DugoutData,
        kbo_data: Optional[DugoutData] = None,
        npb_data: Optional[DugoutData] = None,
        alpha: float = DEFAULT_ALPHA,
        shrink: float = DEFAULT_SHRINK,
        cache_dir: str = "cache/",
    ):
        self._league_data: dict[str, DugoutData] = {"mlb": mlb_data}
        if kbo_data:
            self._league_data["kbo"] = kbo_data
        if npb_data:
            self._league_data["npb"] = npb_data

        self._alpha = alpha
        self._shrink = shrink

        # MLB ID 매핑 (MLB 전용)
        id_mapping = fetch_id_mapping(cache_dir=cache_dir)
        self._mlb_to_fg = build_mlb_to_fg_map(mlb_data, id_mapping)

        # Legacy MLB predictor (하위 호환)
        self._mlb_predictor = DailyPredictor(mlb_data, alpha, shrink, cache_dir)

        leagues = [lid for lid in self._league_data]
        logger.info("MultiLeaguePredictor ready: leagues=%s", leagues)

    def can_predict(self, game: DailyGame) -> bool:
        """해당 경기를 예측할 수 있는지 확인."""
        league_id = getattr(game, "league_id", "mlb")
        data = self._league_data.get(league_id)
        if data is None:
            return False
        return (game.away_team_id in data.teams and
                game.home_team_id in data.teams)

    def predict_game(
        self,
        game: DailyGame,
        n_sims: int = 1000,
        seed: int | None = None,
    ) -> GamePrediction:
        """리그에 따라 적절한 데이터로 경기 예측."""
        league_id = getattr(game, "league_id", "mlb")

        # MLB는 기존 predictor 사용 (ID 매핑 등 복잡한 로직)
        if league_id == "mlb":
            return self._mlb_predictor.predict_game(game, n_sims, seed)

        # KBO/NPB
        data = self._league_data.get(league_id)
        if data is None:
            raise ValueError(f"No data for league: {league_id}")

        if game.away_team_id not in data.teams:
            raise ValueError(f"Unknown team: {game.away_team_id}")
        if game.home_team_id not in data.teams:
            raise ValueError(f"Unknown team: {game.home_team_id}")

        # Seed
        if seed is None:
            if isinstance(game.game_id, int):
                seed = game.game_id % 1_000_000
            else:
                seed = hash(game.game_id) % 1_000_000
        rng = np.random.default_rng(seed)

        # 선발투수 해결
        away_starter, fb_a = _resolve_starter_by_name(
            game.away_starter_name, game.away_team_id, data,
        )
        home_starter, fb_h = _resolve_starter_by_name(
            game.home_starter_name, game.home_team_id, data,
        )

        # 팀 구성
        away_team = _build_game_team_generic(game.away_team_id, away_starter, data)
        home_team = _build_game_team_generic(game.home_team_id, home_starter, data)

        # Park factors
        park = None
        for park_name, pf in data.parks.items():
            # 홈팀 구장 찾기
            if game.home_team_id in park_name or park_name in getattr(game, 'venue', ''):
                park = pf
                break
        if park is None:
            # 팀 매핑에서 구장 찾기
            from data.leagues.kbo.teams import TEAM_MAPPING as KBO_TEAMS
            from data.leagues.npb.teams import TEAM_MAPPING as NPB_TEAMS
            team_map = KBO_TEAMS if league_id == "kbo" else NPB_TEAMS
            team_info = team_map.get(game.home_team_id)
            if team_info:
                park = data.parks.get(team_info["park"])
        if park is None:
            park = ParkFactors(park_name="neutral", pf_1b=100, pf_2b=100, pf_3b=100, pf_hr=100)

        # Quick Sim
        away_team.reset_bullpen()
        home_team.reset_bullpen()
        quick_result = simulate_game(away_team, home_team, park, data.league, rng)

        # Monte Carlo
        mc_series = simulate_series(
            away_team, home_team, park, data.league,
            n_simulations=n_sims,
            seed=int(rng.integers(1_000_000_000)),
        )

        # 팀 기본 승률 블렌딩
        base_away = _build_game_team_generic(
            game.away_team_id, data.teams[game.away_team_id].starter, data,
        )
        base_home = _build_game_team_generic(
            game.home_team_id, data.teams[game.home_team_id].starter, data,
        )
        base_series = simulate_series(
            base_away, base_home, park, data.league,
            n_simulations=200,
            seed=int(rng.integers(1_000_000_000)),
        )

        team_base_pct = base_series.away_win_pct
        game_starter_pct = mc_series.away_win_pct
        blended = self._alpha * team_base_pct + (1 - self._alpha) * game_starter_pct
        final_away = shrink_probability(blended, self._shrink)
        final_home = 1 - final_away

        # 매치업 요약
        fav = game.away_team_id if mc_series.away_win_pct > 0.5 else game.home_team_id
        fav_pct = max(mc_series.away_win_pct, 1 - mc_series.away_win_pct)
        summary = (
            f"{game.away_team_id} ({away_starter.name}) @ "
            f"{game.home_team_id} ({home_starter.name}) | "
            f"Favored: {fav} ({fav_pct:.1%}) | "
            f"Projected: {mc_series.avg_away_runs:.1f}-{mc_series.avg_home_runs:.1f}"
        )

        return GamePrediction(
            game_id=game.game_id,
            game_date=game.game_date,
            away_team_id=game.away_team_id,
            home_team_id=game.home_team_id,
            away_starter_name=away_starter.name,
            home_starter_name=home_starter.name,
            game_time=game.game_time,
            venue=game.venue,
            quick_away_score=quick_result.score["away"],
            quick_home_score=quick_result.score["home"],
            quick_winner=quick_result.winner,
            quick_innings=quick_result.innings_played,
            mc_away_win_pct=mc_series.away_win_pct,
            mc_home_win_pct=mc_series.home_win_pct,
            mc_avg_away_runs=mc_series.avg_away_runs,
            mc_avg_home_runs=mc_series.avg_home_runs,
            mc_avg_total_runs=mc_series.avg_total_runs,
            mc_n_sims=n_sims,
            final_away_win_pct=final_away,
            final_home_win_pct=final_home,
            away_starter_fallback=fb_a,
            home_starter_fallback=fb_h,
            matchup_summary=summary,
        )
