"""스코어링 시스템 테스트."""

import logging
import shutil
import tempfile

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from daily.scoring import calculate_prediction_score, ScoreBreakdown
from daily.store import PredictionStore


def test_scoring_logic():
    """채점 로직 단위 테스트."""
    print("── Scoring Logic Tests ──")

    # 1. 승패 적중 + 정확한 스코어
    s = calculate_prediction_score("away", "away", 5, 3, 5, 3, 0.7)
    assert s.winner_points == 50, f"Expected 50, got {s.winner_points}"
    assert s.exact_score_bonus == 10, f"Expected 10, got {s.exact_score_bonus}"
    assert s.score_points == 40.0, f"Expected 40.0, got {s.score_points}"
    assert s.calibration_points > 0
    print(f"  Perfect prediction: {s.total:.0f} pts (50+40+10+{s.calibration_points:.0f}) ✓")

    # 2. 승패 적중 + 점수 1점 오차
    s = calculate_prediction_score("home", "home", 3, 5, 3, 4, None)
    assert s.winner_points == 50
    assert s.exact_score_bonus == 0
    assert s.score_points > 0
    print(f"  1-run off: {s.total:.0f} pts (50+{s.score_points:.0f}+0) ✓")

    # 3. 승패 틀림
    s = calculate_prediction_score("away", "home", 5, 3, 3, 5, 0.6)
    assert s.winner_points == 0
    assert s.calibration_points < 10
    print(f"  Wrong winner: {s.total:.0f} pts (0+{s.score_points:.0f}+0+{s.calibration_points:.0f}) ✓")

    # 4. 점수 예측 없음
    s = calculate_prediction_score("away", "away", None, None, 4, 2, None)
    assert s.winner_points == 50
    assert s.score_points == 0
    assert s.exact_score_bonus == 0
    print(f"  No score pred: {s.total:.0f} pts (50 only) ✓")

    # 5. 큰 점수 오차
    s = calculate_prediction_score("away", "away", 2, 1, 10, 8, None)
    assert s.score_points == 0  # diff=15, 40 - 15^1.5*5 < 0
    print(f"  Big score miss: {s.total:.0f} pts ✓")

    # 6. 칼리브레이션: 확신 높고 맞음 → 높은 점수
    s1 = calculate_prediction_score("away", "away", None, None, 5, 3, 0.9)
    s2 = calculate_prediction_score("away", "away", None, None, 5, 3, 0.55)
    assert s1.calibration_points > s2.calibration_points, "Higher confidence correct should score higher"
    print(f"  Calibration: 90% conf={s1.calibration_points:.1f}, 55% conf={s2.calibration_points:.1f} ✓")

    # 7. 칼리브레이션: 확신 높고 틀림 → 낮은 점수
    s3 = calculate_prediction_score("away", "home", None, None, 3, 5, 0.9)
    s4 = calculate_prediction_score("away", "home", None, None, 3, 5, 0.55)
    assert s3.calibration_points < s4.calibration_points, "Higher confidence wrong should score lower"
    print(f"  Wrong + high conf={s3.calibration_points:.1f}, low conf={s4.calibration_points:.1f} ✓")

    print()


def test_store_with_scoring():
    """스토어 + 채점 통합 테스트."""
    print("── Store + Scoring Integration ──")

    tmpdir = tempfile.mkdtemp()
    try:
        store = PredictionStore(store_dir=tmpdir)

        # 3경기 예측
        store.submit(1001, "2026-03-25", "NYY", "SFG", "away", 5, 3, 0.65)
        store.submit(1002, "2026-03-25", "BOS", "CIN", "away", 4, 2, 0.60)
        store.submit(1003, "2026-03-25", "LAD", "ARI", "home", 3, 6, 0.55)

        # 결과 기록 + 채점
        b1 = store.record_results(1001, "2026-03-25", "away", 5, 3)
        print(f"  Game 1: exact score! → {b1.total:.0f} pts")
        assert b1.winner_points == 50
        assert b1.exact_score_bonus == 10
        assert b1.score_points == 40.0

        b2 = store.record_results(1002, "2026-03-25", "home", 3, 4)
        print(f"  Game 2: wrong winner → {b2.total:.0f} pts")
        assert b2.winner_points == 0

        b3 = store.record_results(1003, "2026-03-25", "home", 2, 5)
        print(f"  Game 3: right winner, 1-run off → {b3.total:.0f} pts")
        assert b3.winner_points == 50

        # 누적 성적
        stats = store.get_cumulative_stats()
        print(f"\n  Cumulative:")
        print(f"    Predictions: {stats.total_predictions}")
        print(f"    Scored: {stats.total_scored}")
        print(f"    Accuracy: {stats.win_accuracy:.1%} ({stats.wins_correct}/{stats.wins_total})")
        print(f"    Exact scores: {stats.exact_scores}")
        print(f"    Total points: {stats.total_points:.0f}")
        print(f"    Avg points: {stats.avg_points:.1f}")

        assert stats.total_predictions == 3
        assert stats.total_scored == 3
        assert stats.wins_correct == 2
        assert stats.exact_scores == 1
        assert stats.total_points > 0
        print("  ✓ All assertions passed")

        # 날짜별 상세 결과
        date_results = store.get_date_results("2026-03-25")
        assert len(date_results) == 3
        print(f"\n  Date results: {len(date_results)} entries ✓")

    finally:
        shutil.rmtree(tmpdir)
    print()


def test_api_scoring():
    """API 채점 엔드포인트 테스트."""
    print("── API Scoring Tests ──")

    from fastapi.testclient import TestClient
    from server.app import app

    with TestClient(app) as client:
        # Health
        r = client.get("/health")
        assert r.status_code == 200

        # My stats (should be empty)
        r = client.get("/daily/my-stats")
        assert r.status_code == 200
        stats = r.json()
        print(f"  GET /daily/my-stats: {r.status_code} (predictions={stats['total_predictions']})")

        # Date results
        r = client.get("/daily/results/2026-03-25")
        assert r.status_code == 200
        print(f"  GET /daily/results/2026-03-25: {r.status_code}")

        # Yesterday results (with scoring)
        r = client.get("/daily/results/yesterday")
        assert r.status_code == 200
        print(f"  GET /daily/results/yesterday: {r.status_code}")

    print("  ✓ All API tests passed")
    print()


if __name__ == "__main__":
    test_scoring_logic()
    test_store_with_scoring()
    test_api_scoring()
    print("All scoring tests passed!")
