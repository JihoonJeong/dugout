"""방향성 검증 (Sanity Check) 테스트.

모델 결과가 야구 상식에 부합하는지 확인한다.
"""

import pytest

from engine.at_bat import calculate_matchup_probabilities
from engine.models import BatterStats, LeagueStats, ParkFactors, PitcherStats


@pytest.fixture
def league():
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
def neutral():
    return ParkFactors(park_name="Neutral", pf_1b=100, pf_2b=100, pf_3b=100, pf_hr=100)


def _make_avg_batter(**overrides) -> BatterStats:
    defaults = dict(
        player_id="test", name="Test", hand="R", pa=600,
        k_rate=0.224, bb_rate=0.083, hbp_rate=0.012,
        single_rate_bip=0.220, double_rate_bip=0.070, triple_rate_bip=0.007,
        hr_rate_bip=0.045, go_rate_bip=0.345, fo_rate_bip=0.313,
    )
    defaults.update(overrides)
    return BatterStats(**defaults)


def _make_avg_pitcher(**overrides) -> PitcherStats:
    defaults = dict(
        player_id="test", name="Test", hand="R", pa_against=800,
        k_rate=0.224, bb_rate=0.083, hbp_rate=0.012,
        hr_rate_bip=0.045, go_fo_ratio=1.10,
    )
    defaults.update(overrides)
    return PitcherStats(**defaults)


class TestHighKPitcher:
    """고삼진 투수 vs 평균 타자 → K% 리그 평균보다 높아야."""

    def test_high_k_pitcher(self, league, neutral):
        pitcher = _make_avg_pitcher(k_rate=0.32)
        batter = _make_avg_batter()
        probs = calculate_matchup_probabilities(batter, pitcher, league, neutral)
        assert probs["K"] > league.k_rate


class TestPowerHitter:
    """파워 히터 (높은 HR/BIP) vs 평균 투수 → HR 리그 평균보다 높아야."""

    def test_power_hitter(self, league, neutral):
        batter = _make_avg_batter(hr_rate_bip=0.180)
        pitcher = _make_avg_pitcher()
        probs = calculate_matchup_probabilities(batter, pitcher, league, neutral)
        p_bip = 1.0 - probs["K"] - probs["BB"] - probs["HBP"]
        lg_hr_per_pa = p_bip * league.hr_rate_bip
        assert probs["HR"] > lg_hr_per_pa


class TestCoorsField:
    """쿠어스 필드 → HR, 2B 리그 평균보다 높아야."""

    def test_coors(self, league):
        coors = ParkFactors(park_name="Coors", pf_1b=105, pf_2b=120, pf_3b=140, pf_hr=115)
        neutral = ParkFactors(park_name="Neutral", pf_1b=100, pf_2b=100, pf_3b=100, pf_hr=100)
        batter = _make_avg_batter()
        pitcher = _make_avg_pitcher()

        probs_n = calculate_matchup_probabilities(batter, pitcher, league, neutral)
        probs_c = calculate_matchup_probabilities(batter, pitcher, league, coors)

        assert probs_c["HR"] > probs_n["HR"]
        assert probs_c["2B"] > probs_n["2B"]


class TestPlatoonAdvantage:
    """좌완 투수 vs 좌타자 → K%가 좌완 vs 우타자보다 높아야 (일반적으로)."""

    def test_same_hand_higher_k(self, league, neutral):
        lhp = _make_avg_pitcher(hand="L", k_rate=0.240)

        lhb = _make_avg_batter(
            hand="L",
            splits={
                "vs_LHP": {"pa": 150, "k_rate": 0.280, "bb_rate": 0.070, "hbp_rate": 0.010,
                           "single_rate_bip": 0.290, "double_rate_bip": 0.110,
                           "triple_rate_bip": 0.008, "hr_rate_bip": 0.080,
                           "go_rate_bip": 0.310, "fo_rate_bip": 0.202},
                "vs_RHP": {"pa": 450, "k_rate": 0.200, "bb_rate": 0.095, "hbp_rate": 0.010,
                           "single_rate_bip": 0.320, "double_rate_bip": 0.130,
                           "triple_rate_bip": 0.012, "hr_rate_bip": 0.100,
                           "go_rate_bip": 0.260, "fo_rate_bip": 0.178},
            },
        )

        rhb = _make_avg_batter(
            hand="R",
            splits={
                "vs_LHP": {"pa": 200, "k_rate": 0.190, "bb_rate": 0.100, "hbp_rate": 0.010,
                           "single_rate_bip": 0.330, "double_rate_bip": 0.135,
                           "triple_rate_bip": 0.012, "hr_rate_bip": 0.110,
                           "go_rate_bip": 0.250, "fo_rate_bip": 0.163},
                "vs_RHP": {"pa": 400, "k_rate": 0.230, "bb_rate": 0.080, "hbp_rate": 0.010,
                           "single_rate_bip": 0.300, "double_rate_bip": 0.120,
                           "triple_rate_bip": 0.009, "hr_rate_bip": 0.088,
                           "go_rate_bip": 0.290, "fo_rate_bip": 0.193},
            },
        )

        probs_lhb = calculate_matchup_probabilities(lhb, lhp, league, neutral)
        probs_rhb = calculate_matchup_probabilities(rhb, lhp, league, neutral)

        # 좌완 vs 좌타 → K% 높아야
        assert probs_lhb["K"] > probs_rhb["K"]


class TestGroundballPitcher:
    """그라운드볼 투수 → GO 비율 높아야."""

    def test_gb_pitcher(self, league, neutral):
        gb_pitcher = _make_avg_pitcher(go_fo_ratio=1.80)  # 강한 그라운드볼 투수
        batter = _make_avg_batter()
        probs_gb = calculate_matchup_probabilities(batter, gb_pitcher, league, neutral)

        fb_pitcher = _make_avg_pitcher(go_fo_ratio=0.70)  # 플라이볼 투수
        probs_fb = calculate_matchup_probabilities(batter, fb_pitcher, league, neutral)

        assert probs_gb["GO"] > probs_fb["GO"]
        assert probs_fb["FO"] > probs_gb["FO"]
