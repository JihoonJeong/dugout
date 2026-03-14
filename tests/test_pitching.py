"""투수 교체 로직 테스트."""

import numpy as np
import pytest

from engine.models import PitcherState, PitcherStats, Team
from engine.pitching import check_pitching_change, estimate_pitch_count
from tests.conftest import _make_pitcher


def _make_team_with_bullpen(n_relievers: int) -> Team:
    from tests.conftest import _make_batter
    lineup = [_make_batter(f"b{i}", f"Batter {i}") for i in range(9)]
    starter = _make_pitcher("sp", "Starter")
    bullpen = [_make_pitcher(f"rp{i}", f"Reliever {i}") for i in range(n_relievers)]
    return Team(team_id="test", name="Test", lineup=lineup, starter=starter, bullpen=bullpen)


class TestStarterChange:
    def test_change_at_100_pitches(self):
        team = _make_team_with_bullpen(3)
        ps = PitcherState(pitcher=team.starter, pitch_count=100, innings_pitched=5.0, is_starter=True)
        new_ps = check_pitching_change(ps, team)
        assert new_ps is not ps
        assert new_ps.is_starter is False
        assert new_ps.pitch_count == 0

    def test_change_at_6_innings(self):
        team = _make_team_with_bullpen(3)
        ps = PitcherState(pitcher=team.starter, pitch_count=80, innings_pitched=6.0, is_starter=True)
        new_ps = check_pitching_change(ps, team)
        assert new_ps is not ps

    def test_no_change_below_limits(self):
        team = _make_team_with_bullpen(3)
        ps = PitcherState(pitcher=team.starter, pitch_count=80, innings_pitched=5.0, is_starter=True)
        new_ps = check_pitching_change(ps, team)
        assert new_ps is ps


class TestRelieverChange:
    def test_change_after_1_inning(self):
        team = _make_team_with_bullpen(3)
        reliever = team.get_next_reliever()
        ps = PitcherState(pitcher=reliever, pitch_count=15, innings_pitched=1.0, is_starter=False)
        new_ps = check_pitching_change(ps, team)
        assert new_ps is not ps

    def test_no_change_under_1_inning(self):
        team = _make_team_with_bullpen(3)
        reliever = team.get_next_reliever()
        ps = PitcherState(pitcher=reliever, pitch_count=10, innings_pitched=0.67, is_starter=False)
        new_ps = check_pitching_change(ps, team)
        assert new_ps is ps


class TestBullpenExhaustion:
    def test_last_pitcher_stays(self):
        team = _make_team_with_bullpen(1)
        # 유일한 불펜 투수 소진
        team.get_next_reliever()
        ps = PitcherState(
            pitcher=_make_pitcher("last_rp", "Last RP"),
            pitch_count=20, innings_pitched=1.0, is_starter=False,
        )
        new_ps = check_pitching_change(ps, team)
        assert new_ps is ps  # 교체 불가, 현재 투수 유지


class TestPitchCountEstimate:
    def test_returns_positive(self):
        rng = np.random.default_rng(42)
        for event in ["K", "BB", "HBP", "1B", "2B", "3B", "HR", "GO", "FO"]:
            count = estimate_pitch_count(event, rng)
            assert count >= 1

    def test_capped_at_12(self):
        rng = np.random.default_rng(42)
        for _ in range(1000):
            count = estimate_pitch_count("BB", rng)
            assert count <= 12
