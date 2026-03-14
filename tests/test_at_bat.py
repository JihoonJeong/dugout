"""타석 확률 모델 단위 테스트."""

import numpy as np
import pytest

from engine.at_bat import (
    _log5,
    calculate_matchup_probabilities,
    simulate_at_bat,
)
from engine.models import BatterStats, LeagueStats, ParkFactors, PitcherStats


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def league_avg():
    """2024시즌 근사 리그 평균."""
    return LeagueStats(
        season=2024,
        k_rate=0.224,
        bb_rate=0.085,
        hbp_rate=0.010,
        single_rate_bip=0.310,
        double_rate_bip=0.125,
        triple_rate_bip=0.010,
        hr_rate_bip=0.092,
        go_rate_bip=0.280,
        fo_rate_bip=0.183,
        go_fo_ratio=1.10,
    )


@pytest.fixture
def neutral_park():
    """중립 구장."""
    return ParkFactors(park_name="Neutral", pf_1b=100, pf_2b=100, pf_3b=100, pf_hr=100)


@pytest.fixture
def avg_batter():
    """리그 평균 타자."""
    return BatterStats(
        player_id="avg_bat",
        name="Average Batter",
        hand="R",
        pa=600,
        k_rate=0.224,
        bb_rate=0.085,
        hbp_rate=0.010,
        single_rate_bip=0.310,
        double_rate_bip=0.125,
        triple_rate_bip=0.010,
        hr_rate_bip=0.092,
        go_rate_bip=0.280,
        fo_rate_bip=0.183,
    )


@pytest.fixture
def avg_pitcher():
    """리그 평균 투수."""
    return PitcherStats(
        player_id="avg_pit",
        name="Average Pitcher",
        hand="R",
        pa_against=800,
        k_rate=0.224,
        bb_rate=0.085,
        hbp_rate=0.010,
        hr_rate_bip=0.092,
        go_fo_ratio=1.10,
    )


@pytest.fixture
def judge():
    """Aaron Judge (가상 데이터, 스펙 부록 B 기반)."""
    return BatterStats(
        player_id="judge",
        name="Aaron Judge",
        hand="R",
        pa=650,
        k_rate=0.253,
        bb_rate=0.141,
        hbp_rate=0.012,
        single_rate_bip=0.300,
        double_rate_bip=0.120,
        triple_rate_bip=0.010,
        hr_rate_bip=0.180,
        go_rate_bip=0.220,
        fo_rate_bip=0.170,
    )


@pytest.fixture
def cole():
    """Gerrit Cole (가상 데이터, 스펙 부록 B 기반)."""
    return PitcherStats(
        player_id="cole",
        name="Gerrit Cole",
        hand="R",
        pa_against=850,
        k_rate=0.298,
        bb_rate=0.058,
        hbp_rate=0.008,
        hr_rate_bip=0.085,
        go_fo_ratio=0.82,
    )


@pytest.fixture
def yankee_stadium():
    return ParkFactors(park_name="Yankee Stadium", pf_1b=100, pf_2b=95, pf_3b=90, pf_hr=110)


# ---------------------------------------------------------------------------
# 1. 확률 합 검증
# ---------------------------------------------------------------------------

class TestProbabilitySum:
    """모든 매치업에서 9개 이벤트 확률 합 = 1.0."""

    def test_avg_vs_avg(self, avg_batter, avg_pitcher, league_avg, neutral_park):
        probs = calculate_matchup_probabilities(avg_batter, avg_pitcher, league_avg, neutral_park)
        assert abs(sum(probs.values()) - 1.0) < 1e-9

    def test_judge_vs_cole(self, judge, cole, league_avg, yankee_stadium):
        probs = calculate_matchup_probabilities(judge, cole, league_avg, yankee_stadium)
        assert abs(sum(probs.values()) - 1.0) < 1e-9

    def test_all_events_present(self, avg_batter, avg_pitcher, league_avg, neutral_park):
        probs = calculate_matchup_probabilities(avg_batter, avg_pitcher, league_avg, neutral_park)
        expected = {"K", "BB", "HBP", "1B", "2B", "3B", "HR", "GO", "FO"}
        assert set(probs.keys()) == expected

    def test_all_probabilities_positive(self, avg_batter, avg_pitcher, league_avg, neutral_park):
        probs = calculate_matchup_probabilities(avg_batter, avg_pitcher, league_avg, neutral_park)
        for event, p in probs.items():
            assert p > 0, f"P({event}) = {p} <= 0"


# ---------------------------------------------------------------------------
# 2. Log5 단위 테스트
# ---------------------------------------------------------------------------

class TestLog5:
    def test_avg_vs_avg_returns_avg(self):
        """평균 타자 vs 평균 투수 → 리그 평균."""
        result = _log5(0.224, 0.224, 0.224)
        assert abs(result - 0.224) < 1e-9

    def test_high_k_batter_raises_k(self):
        """고삼진 타자는 리그 평균보다 K% 높아야 한다."""
        result = _log5(0.35, 0.224, 0.224)
        assert result > 0.224

    def test_high_k_pitcher_raises_k(self):
        """고삼진 투수는 리그 평균보다 K% 높아야 한다."""
        result = _log5(0.224, 0.35, 0.224)
        assert result > 0.224

    def test_symmetry(self):
        """타자와 투수 입력 교환 시 동일 결과."""
        r1 = _log5(0.30, 0.20, 0.25)
        r2 = _log5(0.20, 0.30, 0.25)
        assert abs(r1 - r2) < 1e-9


# ---------------------------------------------------------------------------
# 3. 범위 검증
# ---------------------------------------------------------------------------

class TestProbabilityRanges:
    def test_k_range(self, judge, cole, league_avg, yankee_stadium):
        probs = calculate_matchup_probabilities(judge, cole, league_avg, yankee_stadium)
        assert 0.05 <= probs["K"] <= 0.50

    def test_bb_range(self, judge, cole, league_avg, yankee_stadium):
        probs = calculate_matchup_probabilities(judge, cole, league_avg, yankee_stadium)
        assert 0.02 <= probs["BB"] <= 0.25

    def test_hr_range(self, judge, cole, league_avg, yankee_stadium):
        probs = calculate_matchup_probabilities(judge, cole, league_avg, yankee_stadium)
        assert 0.001 <= probs["HR"] <= 0.15

    def test_individual_prob_bounds(self, avg_batter, avg_pitcher, league_avg, neutral_park):
        probs = calculate_matchup_probabilities(avg_batter, avg_pitcher, league_avg, neutral_park)
        for event, p in probs.items():
            assert 0.001 <= p <= 0.95, f"P({event}) = {p} out of [0.001, 0.95]"


# ---------------------------------------------------------------------------
# 4. 리그 평균 복원
# ---------------------------------------------------------------------------

class TestLeagueAverageRestoration:
    def test_avg_vs_avg_matches_league(self, avg_batter, avg_pitcher, league_avg, neutral_park):
        """평균 타자 vs 평균 투수 in 중립 구장 → 리그 평균과 일치."""
        probs = calculate_matchup_probabilities(avg_batter, avg_pitcher, league_avg, neutral_park)

        # Stage 1 이벤트는 정확히 리그 평균이어야 함
        assert abs(probs["K"] - league_avg.k_rate) < 0.001
        assert abs(probs["BB"] - league_avg.bb_rate) < 0.001
        assert abs(probs["HBP"] - league_avg.hbp_rate) < 0.001


# ---------------------------------------------------------------------------
# 5. simulate_at_bat 테스트
# ---------------------------------------------------------------------------

class TestSimulateAtBat:
    def test_returns_valid_event(self, avg_batter, avg_pitcher, league_avg, neutral_park):
        rng = np.random.default_rng(42)
        result = simulate_at_bat(avg_batter, avg_pitcher, league_avg, neutral_park, rng)
        assert result.event in {"K", "BB", "HBP", "1B", "2B", "3B", "HR", "GO", "FO"}

    def test_reproducibility(self, avg_batter, avg_pitcher, league_avg, neutral_park):
        """동일 시드 → 동일 결과."""
        r1 = simulate_at_bat(avg_batter, avg_pitcher, league_avg, neutral_park, np.random.default_rng(42))
        r2 = simulate_at_bat(avg_batter, avg_pitcher, league_avg, neutral_park, np.random.default_rng(42))
        assert r1.event == r2.event

    def test_probabilities_included(self, avg_batter, avg_pitcher, league_avg, neutral_park):
        rng = np.random.default_rng(42)
        result = simulate_at_bat(avg_batter, avg_pitcher, league_avg, neutral_park, rng)
        assert len(result.probabilities) == 9
        assert abs(sum(result.probabilities.values()) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# 6. Platoon split 테스트
# ---------------------------------------------------------------------------

class TestPlatoonSplit:
    def test_switch_hitter_vs_rhp(self, league_avg, neutral_park, avg_pitcher):
        """스위치 히터 vs RHP → 좌타석 splits 사용."""
        batter = BatterStats(
            player_id="switch", name="Switch Hitter", hand="S", pa=500,
            k_rate=0.200, bb_rate=0.100, hbp_rate=0.010,
            single_rate_bip=0.310, double_rate_bip=0.125, triple_rate_bip=0.010,
            hr_rate_bip=0.092, go_rate_bip=0.280, fo_rate_bip=0.183,
            splits={
                "vs_RHP": {"pa": 350, "k_rate": 0.180, "bb_rate": 0.110, "hbp_rate": 0.010,
                           "single_rate_bip": 0.320, "double_rate_bip": 0.130,
                           "triple_rate_bip": 0.012, "hr_rate_bip": 0.100,
                           "go_rate_bip": 0.270, "fo_rate_bip": 0.168},
                "vs_LHP": {"pa": 150, "k_rate": 0.230, "bb_rate": 0.085, "hbp_rate": 0.010,
                           "single_rate_bip": 0.290, "double_rate_bip": 0.115,
                           "triple_rate_bip": 0.008, "hr_rate_bip": 0.080,
                           "go_rate_bip": 0.300, "fo_rate_bip": 0.207},
            },
        )
        probs = calculate_matchup_probabilities(batter, avg_pitcher, league_avg, neutral_park)
        assert abs(sum(probs.values()) - 1.0) < 1e-9
        # 스위치 히터 vs RHP → vs_RHP split 사용 → K% 낮아야 함
        assert probs["K"] < 0.224  # 리그 평균보다 낮음 (split K%=18%)

    def test_small_sample_regression(self, league_avg, neutral_park, avg_pitcher):
        """소표본 split은 overall 쪽으로 회귀."""
        batter = BatterStats(
            player_id="small", name="Small Sample", hand="R", pa=500,
            k_rate=0.200, bb_rate=0.100, hbp_rate=0.010,
            single_rate_bip=0.310, double_rate_bip=0.125, triple_rate_bip=0.010,
            hr_rate_bip=0.092, go_rate_bip=0.280, fo_rate_bip=0.183,
            splits={
                "vs_RHP": {
                    "pa": 30,  # 소표본
                    "k_rate": 0.400,  # 극단적으로 높은 K%
                    "bb_rate": 0.050, "hbp_rate": 0.010,
                    "single_rate_bip": 0.310, "double_rate_bip": 0.125,
                    "triple_rate_bip": 0.010, "hr_rate_bip": 0.092,
                    "go_rate_bip": 0.280, "fo_rate_bip": 0.183,
                },
            },
        )
        probs = calculate_matchup_probabilities(batter, avg_pitcher, league_avg, neutral_park)
        # 30/100 = 0.3 weight → blended K% ≈ 0.3*0.4 + 0.7*0.2 = 0.26
        # Log5로 리그 평균과 결합하므로 정확히 0.26은 아니지만, 0.4보다는 훨씬 낮아야
        assert probs["K"] < 0.35


# ---------------------------------------------------------------------------
# 7. Park Factor 테스트
# ---------------------------------------------------------------------------

class TestParkFactor:
    def test_coors_field_boosts_hr(self, avg_batter, avg_pitcher, league_avg, neutral_park):
        """쿠어스 필드 → HR 상승."""
        coors = ParkFactors(park_name="Coors Field", pf_1b=105, pf_2b=120, pf_3b=140, pf_hr=115)
        probs_neutral = calculate_matchup_probabilities(avg_batter, avg_pitcher, league_avg, neutral_park)
        probs_coors = calculate_matchup_probabilities(avg_batter, avg_pitcher, league_avg, coors)
        assert probs_coors["HR"] > probs_neutral["HR"]
        assert probs_coors["2B"] > probs_neutral["2B"]

    def test_no_park_effect_with_neutral(self, avg_batter, avg_pitcher, league_avg, neutral_park):
        """중립 구장은 보정 없음."""
        probs = calculate_matchup_probabilities(avg_batter, avg_pitcher, league_avg, neutral_park)
        # 평균 vs 평균 + 중립 → 거의 리그 평균
        p_bip = 1.0 - probs["K"] - probs["BB"] - probs["HBP"]
        hr_given_bip = probs["HR"] / p_bip
        assert abs(hr_given_bip - league_avg.hr_rate_bip) < 0.01
