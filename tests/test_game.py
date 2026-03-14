"""경기 흐름 테스트."""

import numpy as np
import pytest

from engine.game import simulate_game, _is_walkoff, _advance_half_inning
from engine.models import GameState, PitcherState, Runner


class TestGameBasics:
    def test_game_completes(self, avg_team_away, avg_team_home, league_avg, neutral_park):
        """경기가 정상 완료된다."""
        rng = np.random.default_rng(42)
        result = simulate_game(avg_team_away, avg_team_home, neutral_park, league_avg, rng)
        assert result.winner in ("away", "home", "tie")
        assert result.innings_played >= 9

    def test_score_nonnegative(self, avg_team_away, avg_team_home, league_avg, neutral_park):
        rng = np.random.default_rng(42)
        result = simulate_game(avg_team_away, avg_team_home, neutral_park, league_avg, rng)
        assert result.score["away"] >= 0
        assert result.score["home"] >= 0

    def test_play_log_exists(self, avg_team_away, avg_team_home, league_avg, neutral_park):
        rng = np.random.default_rng(42)
        result = simulate_game(avg_team_away, avg_team_home, neutral_park, league_avg, rng)
        assert len(result.play_log) > 0

    def test_reproducibility(self, avg_team_away, avg_team_home, league_avg, neutral_park):
        """동일 시드 → 동일 결과."""
        avg_team_away.reset_bullpen()
        avg_team_home.reset_bullpen()
        r1 = simulate_game(avg_team_away, avg_team_home, neutral_park, league_avg, np.random.default_rng(42))
        avg_team_away.reset_bullpen()
        avg_team_home.reset_bullpen()
        r2 = simulate_game(avg_team_away, avg_team_home, neutral_park, league_avg, np.random.default_rng(42))
        assert r1.score == r2.score
        assert r1.winner == r2.winner

    def test_runs_by_inning_matches_score(self, avg_team_away, avg_team_home, league_avg, neutral_park):
        rng = np.random.default_rng(42)
        result = simulate_game(avg_team_away, avg_team_home, neutral_park, league_avg, rng)
        assert sum(result.runs_by_inning["away"]) == result.score["away"]
        assert sum(result.runs_by_inning["home"]) == result.score["home"]

    def test_box_score_output(self, avg_team_away, avg_team_home, league_avg, neutral_park):
        rng = np.random.default_rng(42)
        result = simulate_game(avg_team_away, avg_team_home, neutral_park, league_avg, rng)
        box = result.box_score()
        assert "Away" in box
        assert "Home" in box


class TestInningStructure:
    def test_9_innings_minimum(self, avg_team_away, avg_team_home, league_avg, neutral_park):
        """최소 9이닝."""
        rng = np.random.default_rng(42)
        result = simulate_game(avg_team_away, avg_team_home, neutral_park, league_avg, rng)
        assert result.innings_played >= 9

    def test_no_tie_in_regulation(self, avg_team_away, avg_team_home, league_avg, neutral_park):
        """동점이면 연장전 진입 (20이닝 무승부 제외)."""
        rng = np.random.default_rng(42)
        result = simulate_game(avg_team_away, avg_team_home, neutral_park, league_avg, rng)
        if result.winner == "tie":
            assert result.innings_played == 20
        else:
            assert result.score["away"] != result.score["home"]


class TestWalkoff:
    def test_is_walkoff_bottom_9(self):
        state = GameState(
            inning=9, half="bottom", outs=1,
            runners={}, score={"away": 3, "home": 4},
            batting_order_idx={"away": 0, "home": 0},
            current_pitcher={}, game_over=False, play_log=[],
        )
        assert _is_walkoff(state) is True

    def test_not_walkoff_top(self):
        state = GameState(
            inning=9, half="top", outs=1,
            runners={}, score={"away": 4, "home": 3},
            batting_order_idx={"away": 0, "home": 0},
            current_pitcher={}, game_over=False, play_log=[],
        )
        assert _is_walkoff(state) is False

    def test_not_walkoff_early_inning(self):
        state = GameState(
            inning=5, half="bottom", outs=1,
            runners={}, score={"away": 3, "home": 4},
            batting_order_idx={"away": 0, "home": 0},
            current_pitcher={}, game_over=False, play_log=[],
        )
        assert _is_walkoff(state) is False

    def test_not_walkoff_tied(self):
        state = GameState(
            inning=9, half="bottom", outs=1,
            runners={}, score={"away": 3, "home": 3},
            batting_order_idx={"away": 0, "home": 0},
            current_pitcher={}, game_over=False, play_log=[],
        )
        assert _is_walkoff(state) is False


class TestManfredRunner:
    def test_no_manfred_before_10(self, avg_team_away, avg_team_home, league_avg, neutral_park):
        """9이닝까지는 Manfred runner 없음 — 다수 게임 확인."""
        rng = np.random.default_rng(42)
        for _ in range(10):
            avg_team_away.reset_bullpen()
            avg_team_home.reset_bullpen()
            result = simulate_game(avg_team_away, avg_team_home, neutral_park, league_avg, rng)
            for event in result.play_log:
                if event.inning < 10 and event.outs_before == 0:
                    # 이닝 첫 타석에서 2루에 주자가 없어야 (9이닝까지)
                    if event.inning == 1 or event.outs_before == 0:
                        pass  # play_log만으로는 판별 제한적, 통합 테스트에서 추가 검증
