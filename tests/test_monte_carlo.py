"""Monte Carlo 시뮬레이션 테스트."""

import numpy as np
import pytest

from engine.monte_carlo import simulate_series


class TestMonteCarlo:
    def test_series_completes(self, avg_team_away, avg_team_home, league_avg, neutral_park):
        result = simulate_series(avg_team_away, avg_team_home, neutral_park, league_avg, n_simulations=10, seed=42)
        assert len(result.results) == 10

    def test_win_pct_sums_to_near_1(self, avg_team_away, avg_team_home, league_avg, neutral_park):
        result = simulate_series(avg_team_away, avg_team_home, neutral_park, league_avg, n_simulations=50, seed=42)
        # tie 가능성이 있으므로 <= 1.0
        assert result.away_win_pct + result.home_win_pct <= 1.0 + 1e-9

    def test_summary_keys(self, avg_team_away, avg_team_home, league_avg, neutral_park):
        result = simulate_series(avg_team_away, avg_team_home, neutral_park, league_avg, n_simulations=10, seed=42)
        s = result.summary()
        assert "n_simulations" in s
        assert "away_win_pct" in s
        assert "avg_total_runs" in s

    def test_avg_runs_reasonable(self, avg_team_away, avg_team_home, league_avg, neutral_park):
        """평균 득점이 합리적 범위."""
        result = simulate_series(avg_team_away, avg_team_home, neutral_park, league_avg, n_simulations=100, seed=42)
        assert 2.0 < result.avg_total_runs < 20.0

    def test_score_distribution(self, avg_team_away, avg_team_home, league_avg, neutral_park):
        result = simulate_series(avg_team_away, avg_team_home, neutral_park, league_avg, n_simulations=50, seed=42)
        dist = result.score_distribution("away")
        assert abs(sum(dist.values()) - 1.0) < 1e-9
