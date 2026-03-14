"""공통 테스트 fixtures."""

import pytest

from engine.models import BatterStats, LeagueStats, ParkFactors, PitcherStats, Team


@pytest.fixture
def league_avg():
    # 현실적 2024 MLB 근사값 (BIP 내 GO+FO ≈ 66%, BABIP ≈ .300)
    return LeagueStats(
        season=2024,
        k_rate=0.224,
        bb_rate=0.083,
        hbp_rate=0.012,
        single_rate_bip=0.220,
        double_rate_bip=0.070,
        triple_rate_bip=0.007,
        hr_rate_bip=0.045,
        go_rate_bip=0.345,
        fo_rate_bip=0.313,
        go_fo_ratio=1.10,
    )


@pytest.fixture
def neutral_park():
    return ParkFactors(park_name="Neutral", pf_1b=100, pf_2b=100, pf_3b=100, pf_hr=100)


def _make_batter(player_id: str, name: str, **overrides) -> BatterStats:
    defaults = dict(
        player_id=player_id, name=name, hand="R", pa=600,
        k_rate=0.224, bb_rate=0.083, hbp_rate=0.012,
        single_rate_bip=0.220, double_rate_bip=0.070, triple_rate_bip=0.007,
        hr_rate_bip=0.045, go_rate_bip=0.345, fo_rate_bip=0.313,
    )
    defaults.update(overrides)
    return BatterStats(**defaults)


def _make_pitcher(player_id: str, name: str, **overrides) -> PitcherStats:
    defaults = dict(
        player_id=player_id, name=name, hand="R", pa_against=800,
        k_rate=0.224, bb_rate=0.083, hbp_rate=0.012,
        hr_rate_bip=0.045, go_fo_ratio=1.10,
    )
    defaults.update(overrides)
    return PitcherStats(**defaults)


@pytest.fixture
def avg_team_away():
    lineup = [_make_batter(f"away_b{i}", f"Away Batter {i+1}") for i in range(9)]
    starter = _make_pitcher("away_sp", "Away Starter")
    bullpen = [_make_pitcher(f"away_rp{i}", f"Away Reliever {i+1}") for i in range(5)]
    return Team(team_id="away", name="Away Team", lineup=lineup, starter=starter, bullpen=bullpen)


@pytest.fixture
def avg_team_home():
    lineup = [_make_batter(f"home_b{i}", f"Home Batter {i+1}") for i in range(9)]
    starter = _make_pitcher("home_sp", "Home Starter")
    bullpen = [_make_pitcher(f"home_rp{i}", f"Home Reliever {i+1}") for i in range(5)]
    return Team(team_id="home", name="Home Team", lineup=lineup, starter=starter, bullpen=bullpen)
