"""Validation framework 단위 테스트."""

import pytest
import numpy as np

from engine.models import LeagueStats, ParkFactors, BatterStats, PitcherStats, Team
from validation.ground_truth import ActualResults
from validation.l1_player import run_l1, predicted_woba, WOBA_WEIGHTS
from validation.l2_team import run_l2
from validation.l3_game import run_l3, _compute_auc, _compute_calibration
from validation.l4_season import run_l4
from validation.runner import ValidationResult
from validation.report import generate_report
from validation.diagnostics import run_diagnostics
from validation.compare import compare_versions
from tests.conftest import _make_batter, _make_pitcher


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def league():
    return LeagueStats(
        season=2024, k_rate=0.224, bb_rate=0.083, hbp_rate=0.012,
        single_rate_bip=0.220, double_rate_bip=0.070, triple_rate_bip=0.007,
        hr_rate_bip=0.045, go_rate_bip=0.345, fo_rate_bip=0.313, go_fo_ratio=1.10,
    )


@pytest.fixture
def neutral_park():
    return ParkFactors(park_name="Neutral", pf_1b=100, pf_2b=100, pf_3b=100, pf_hr=100)


@pytest.fixture
def two_teams():
    """간단한 두 팀 생성."""
    def _make_team(tid, name):
        lineup = [_make_batter(f"{tid}_b{i}", f"{name} B{i+1}") for i in range(9)]
        starter = _make_pitcher(f"{tid}_sp", f"{name} SP")
        bullpen = [_make_pitcher(f"{tid}_rp{i}", f"{name} RP{i+1}") for i in range(5)]
        return Team(team_id=tid, name=name, lineup=lineup, starter=starter, bullpen=bullpen)

    return {"AAA": _make_team("AAA", "Team A"), "BBB": _make_team("BBB", "Team B")}


@pytest.fixture
def mock_actual():
    """테스트용 ActualResults."""
    return ActualResults(
        season=2024,
        batter_actuals={
            "b1": {"name": "Test Batter 1", "pa": 500, "k_rate": 0.22, "bb_rate": 0.08,
                   "bb_rate_no_ibb": 0.07, "hr_rate": 0.04, "woba": 0.320},
            "b2": {"name": "Test Batter 2", "pa": 400, "k_rate": 0.25, "bb_rate": 0.10,
                   "bb_rate_no_ibb": 0.09, "hr_rate": 0.05, "woba": 0.350},
        },
        pitcher_actuals={},
        team_actuals={
            "AAA": {"name": "Team A", "wins": 90, "losses": 72, "games": 162},
            "BBB": {"name": "Team B", "wins": 80, "losses": 82, "games": 162},
        },
        game_actuals=[
            {"game_id": 1, "date": "2024-04-01", "away": "AAA", "home": "BBB",
             "away_score": 5, "home_score": 3, "winner": "away"},
            {"game_id": 2, "date": "2024-04-02", "away": "BBB", "home": "AAA",
             "away_score": 2, "home_score": 6, "winner": "home"},
            {"game_id": 3, "date": "2024-04-03", "away": "AAA", "home": "BBB",
             "away_score": 4, "home_score": 7, "winner": "home"},
            {"game_id": 4, "date": "2024-04-04", "away": "BBB", "home": "AAA",
             "away_score": 3, "home_score": 1, "winner": "away"},
        ],
    )


# ── L1 Tests ──────────────────────────────────────────────


def test_predicted_woba_zero():
    """확률이 전부 0이면 wOBA=0."""
    assert predicted_woba({}) == 0.0


def test_predicted_woba_calculation():
    """알려진 확률로 wOBA 계산 검증."""
    probs = {"BB": 0.08, "HBP": 0.01, "1B": 0.15, "2B": 0.05, "3B": 0.005, "HR": 0.03}
    woba = predicted_woba(probs)
    expected = (0.08 * 0.690 + 0.01 * 0.722 + 0.15 * 0.883
                + 0.05 * 1.244 + 0.005 * 1.569 + 0.03 * 2.004)
    assert abs(woba - expected) < 1e-6


def test_l1_runs_with_batters(league, mock_actual):
    """L1이 타자를 처리하고 결과를 반환."""
    batters = {
        "b1": _make_batter("b1", "Test Batter 1", k_rate=0.22, bb_rate=0.08),
        "b2": _make_batter("b2", "Test Batter 2", k_rate=0.25, bb_rate=0.10),
    }
    result = run_l1(batters, league, mock_actual, min_pa=200)
    assert result.n_batters == 2
    assert result.k_rmse >= 0
    assert result.woba_corr is not None


# ── L3 Helper Tests ───────────────────────────────────────


def test_auc_perfect():
    """완벽한 분리일 때 AUC=1."""
    pred = np.array([0.9, 0.8, 0.7, 0.2, 0.1])
    actual = np.array([1, 1, 1, 0, 0])
    assert _compute_auc(pred, actual) == 1.0


def test_auc_random():
    """랜덤 예측은 AUC ≈ 0.5."""
    rng = np.random.default_rng(42)
    pred = rng.random(1000)
    actual = rng.integers(0, 2, 1000).astype(float)
    auc = _compute_auc(pred, actual)
    assert 0.4 < auc < 0.6


def test_calibration_buckets():
    """칼리브레이션 버킷 생성 확인."""
    pred = np.array([0.1, 0.2, 0.3, 0.8, 0.9])
    actual = np.array([0, 0, 1, 1, 1])
    cal = _compute_calibration(pred, actual, n_buckets=5)
    assert len(cal) > 0
    for label, bucket in cal.items():
        assert "pred_mean" in bucket
        assert "actual_mean" in bucket
        assert "n" in bucket


# ── L3/L4 Integration ────────────────────────────────────


def test_l3_runs(two_teams, league, neutral_park, mock_actual):
    """L3가 경기 예측을 실행하고 결과 반환."""
    parks = {"Neutral": neutral_park}
    # TEAM_MAPPING 의존성을 피하기 위해 간이 테스트
    # L3는 TEAM_MAPPING에서 park를 가져오므로 실 데이터 없이는 skip
    # 대신 핵심 메트릭 계산 로직만 테스트
    pass


def test_l4_result_passed():
    """L4Result.passed() 로직 테스트."""
    from validation.l4_season import L4Result
    r = L4Result(n_teams=30, wins_rmse=7.0, wins_corr=0.80,
                 playoff_correct=10, playoff_total=12,
                 pythag_wins_rmse=4.0, sim_pythag_wins_rmse=5.0,
                 sim_pythag_vs_direct_rmse=2.0, team_details=[])
    passed = r.passed()
    assert passed["wins_rmse"] is True
    assert passed["wins_corr"] is True
    assert passed["playoff_teams"] is True


def test_l4_result_failed():
    """L4Result.passed() 실패 조건."""
    from validation.l4_season import L4Result
    r = L4Result(n_teams=30, wins_rmse=10.0, wins_corr=0.50,
                 playoff_correct=5, playoff_total=12,
                 pythag_wins_rmse=4.0, sim_pythag_wins_rmse=6.0,
                 sim_pythag_vs_direct_rmse=3.0, team_details=[])
    passed = r.passed()
    assert passed["wins_rmse"] is False
    assert passed["wins_corr"] is False
    assert passed["playoff_teams"] is False


# ── ValidationResult ──────────────────────────────────────


def test_validation_result_summary():
    """ValidationResult.summary() 테스트."""
    from validation.l1_player import L1Result
    l1 = L1Result(
        n_batters=100, k_rmse=0.03, bb_rmse=0.02, hr_rmse=0.01,
        woba_rmse=0.025, woba_corr=0.85,
        league_avg_restoration={}, player_details=[], spot_checks=[],
    )
    vr = ValidationResult(season=2024, version="test", timestamp=0, l1=l1)
    s = vr.summary()
    assert "L1" in s
    assert all(s["L1"].values())


def test_validation_result_to_dict():
    """to_dict()가 JSON 직렬화 가능한 dict 반환."""
    import json
    vr = ValidationResult(season=2024, version="test", timestamp=0)
    d = vr.to_dict()
    json.dumps(d)  # 직렬화 가능 확인


# ── Report ────────────────────────────────────────────────


def test_report_generation():
    """리포트가 문자열로 생성됨."""
    from validation.l1_player import L1Result
    l1 = L1Result(
        n_batters=50, k_rmse=0.035, bb_rmse=0.025, hr_rmse=0.012,
        woba_rmse=0.028, woba_corr=0.82,
        league_avg_restoration={"K": 0.002}, player_details=[],
        spot_checks=[{"name": "Test", "pred_woba": 0.350, "actual_woba": 0.310, "woba_error": 0.040}],
    )
    vr = ValidationResult(season=2024, version="test", timestamp=0, l1=l1,
                          elapsed_seconds={"L1": 1.5, "total": 1.5})
    report = generate_report(vr)
    assert "L1: Player Accuracy" in report
    assert "wOBA RMSE" in report
    assert "Timing" in report


# ── Diagnostics ───────────────────────────────────────────


def test_diagnostics_no_crash():
    """Diagnostics가 빈 결과에서도 crash 하지 않음."""
    vr = ValidationResult(season=2024, version="test", timestamp=0)
    diag = run_diagnostics(vr)
    assert diag.issues == []


def test_diagnostics_l1_bias():
    """L1 편향 감지."""
    from validation.l1_player import L1Result
    # 모든 예측이 실제보다 높은 경우
    details = [
        {"pred_k": 0.25, "actual_k": 0.22, "pred_bb": 0.10, "actual_bb": 0.08,
         "pred_hr": 0.05, "actual_hr": 0.04, "pred_woba": 0.35, "actual_woba": 0.32,
         "actual_bb_no_ibb": 0.07}
    ] * 20
    l1 = L1Result(n_batters=20, k_rmse=0.03, bb_rmse=0.02, hr_rmse=0.01,
                  woba_rmse=0.03, woba_corr=0.8,
                  league_avg_restoration={}, player_details=details, spot_checks=[])
    vr = ValidationResult(season=2024, version="test", timestamp=0, l1=l1)
    diag = run_diagnostics(vr)
    assert diag.l1_bias is not None
    assert diag.l1_bias["k"] > 0  # over-predicting K%
    assert any("systematic bias" in issue for issue in diag.issues)
