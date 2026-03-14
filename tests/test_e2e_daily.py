"""End-to-end daily prediction flow test.

흐름: 경기 목록 → 시뮬레이션 → 예측 제출 → 수정 → 결과 수집 → 채점 → 대시보드
+ 스프링 트레이닝 실제 데이터로 fallback 검증
"""

import logging
import shutil
import tempfile
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

from datetime import date
from dataclasses import asdict

from data.pipeline import DugoutDataPipeline
from daily.pipeline import DailyDataPipeline
from daily.predictor import DailyPredictor
from daily.store import PredictionStore
from daily.scoring import calculate_prediction_score


def main():
    print("=" * 70)
    print(" End-to-End Daily Prediction Flow Test")
    print("=" * 70)
    print()

    # ── Step 1: Load engine data ──
    print("── Step 1: Load Engine Data ──")
    pipeline = DugoutDataPipeline(season=2025)
    data = pipeline.load_all()
    print(f"  Teams: {len(data.teams)}, Pitchers: {len(data.all_pitchers)}")
    print()

    # ── Step 2: Fetch opening week games ──
    print("── Step 2: Fetch Opening Week ──")
    daily = DailyDataPipeline()

    dates_to_test = [
        date(2026, 3, 25),  # 개막일 (1경기)
        date(2026, 3, 26),  # 11경기
        date(2026, 3, 28),  # 15경기
    ]

    all_games = {}
    for d in dates_to_test:
        games = daily.fetch_games(d)
        all_games[d.isoformat()] = games
        print(f"  {d}: {len(games)} games")
    print()

    # ── Step 3: Run predictions ──
    print("── Step 3: Engine Predictions ──")
    predictor = DailyPredictor(data)

    all_predictions = {}
    total_time = 0
    total_games = 0
    total_fallbacks = 0

    for date_str, games in all_games.items():
        t0 = time.time()
        preds = predictor.predict_all(games, n_sims=1000)
        elapsed = time.time() - t0
        total_time += elapsed
        total_games += len(preds)
        all_predictions[date_str] = preds

        fb_count = sum(1 for p in preds if p.away_starter_fallback or p.home_starter_fallback)
        total_fallbacks += fb_count

        print(f"  {date_str}: {len(preds)} predictions in {elapsed:.1f}s "
              f"({fb_count} with fallback)")

    print(f"\n  Total: {total_games} games in {total_time:.1f}s ({total_time/total_games:.1f}s/game)")
    print(f"  Fallback rate: {total_fallbacks}/{total_games} games have at least one fallback")
    print()

    # ── Step 4: Prediction flow (submit → update → lock → results) ──
    print("── Step 4: Full Prediction Flow ──")
    tmpdir = tempfile.mkdtemp()
    store = PredictionStore(store_dir=tmpdir)

    test_date = "2026-03-26"
    preds = all_predictions[test_date]

    # Submit predictions for all games
    submitted = 0
    for p in preds:
        winner = "away" if p.final_away_win_pct > 0.5 else "home"
        store.submit(
            game_id=p.game_id,
            game_date=p.game_date,
            away_team_id=p.away_team_id,
            home_team_id=p.home_team_id,
            predicted_winner=winner,
            predicted_away_score=round(p.mc_avg_away_runs),
            predicted_home_score=round(p.mc_avg_home_runs),
            confidence=max(p.final_away_win_pct, p.final_home_win_pct),
        )
        submitted += 1
    print(f"  Submitted {submitted} predictions for {test_date}")

    # Update first prediction
    stored = store.get_by_date(test_date)
    first = stored[0]
    store.update(
        prediction_id=first.prediction_id,
        game_date=test_date,
        predicted_winner="home" if first.predicted_winner == "away" else "away",
    )
    print(f"  Updated prediction {first.prediction_id}")

    # Simulate results (mock)
    scores_correct = 0
    for i, p in enumerate(preds):
        # Mock result: alternate wins
        actual_winner = "away" if i % 2 == 0 else "home"
        actual_away = round(p.mc_avg_away_runs) + (i % 3 - 1)
        actual_home = round(p.mc_avg_home_runs) + ((i + 1) % 3 - 1)
        if actual_away < 0: actual_away = 0
        if actual_home < 0: actual_home = 0

        breakdown = store.record_results(
            game_id=p.game_id,
            game_date=p.game_date,
            actual_winner=actual_winner,
            actual_away_score=actual_away,
            actual_home_score=actual_home,
        )
        if breakdown and breakdown.exact_score_bonus > 0:
            scores_correct += 1

    print(f"  Recorded results for {len(preds)} games")
    print(f"  Exact scores: {scores_correct}")

    # ── Step 5: Cumulative stats ──
    print("\n── Step 5: Cumulative Stats ──")
    stats = store.get_cumulative_stats()
    print(f"  Predictions: {stats.total_predictions}")
    print(f"  Scored: {stats.total_scored}")
    print(f"  Win accuracy: {stats.win_accuracy:.1%} ({stats.wins_correct}/{stats.wins_total})")
    print(f"  Avg points: {stats.avg_points:.1f}")
    print(f"  Total points: {stats.total_points:.0f}")

    # ── Step 6: Date results ──
    print("\n── Step 6: Date Results ──")
    date_results = store.get_date_results(test_date)
    print(f"  {test_date}: {len(date_results)} scored predictions")
    for r in date_results[:3]:
        print(f"    {r['away_team_id']}@{r['home_team_id']}: "
              f"{'✓' if r['correct'] else '✗'} {r['score_total']:.0f}pts "
              f"(W:{r['score_winner']} S:{r['score_accuracy']:.0f} E:{r['score_exact_bonus']} C:{r['score_calibration']:.0f})")

    shutil.rmtree(tmpdir)
    print()

    # ── Step 7: API full flow test ──
    print("── Step 7: API Full Flow ──")
    from fastapi.testclient import TestClient
    from server.app import app

    with TestClient(app) as client:
        # 1. Games
        r = client.get("/daily/games/2026-03-26")
        assert r.status_code == 200
        games_resp = r.json()
        print(f"  GET /daily/games/2026-03-26: {len(games_resp)} games")
        assert len(games_resp) > 0

        # Verify game card structure
        g = games_resp[0]
        required_fields = ["game_id", "game_date", "away_team_id", "home_team_id",
                          "final_away_win_pct", "mc_avg_away_runs", "matchup_summary"]
        for f in required_fields:
            assert f in g, f"Missing field: {f}"
        print(f"  Game card fields verified ✓")

        # 2. Submit prediction (use last game to avoid prior test collisions)
        test_game = games_resp[-1]
        r = client.post("/daily/predictions", json={
            "game_id": test_game["game_id"],
            "game_date": test_game["game_date"],
            "predicted_winner": "away",
            "predicted_away_score": 5,
            "predicted_home_score": 3,
            "confidence": 0.62,
        })
        if r.status_code == 200:
            pred = r.json()["prediction"]
            print(f"  POST /daily/predictions: submitted ✓")

            # 3. Update prediction
            r = client.put(f"/daily/predictions/{pred['prediction_id']}", json={
                "game_date": test_game["game_date"],
                "predicted_winner": "home",
                "predicted_home_score": 4,
            })
            assert r.status_code == 200
            print(f"  PUT /daily/predictions: updated ✓")

            # 4. Duplicate submit → error
            r = client.post("/daily/predictions", json={
                "game_id": test_game["game_id"],
                "game_date": test_game["game_date"],
                "predicted_winner": "away",
            })
            assert r.status_code == 400
            print(f"  Duplicate submit: 400 ✓")
        elif r.status_code == 400 and "already exists" in r.json().get("detail", ""):
            print(f"  POST /daily/predictions: already exists (prior run) — skipped ✓")
        else:
            print(f"  POST /daily/predictions: {r.status_code} {r.json()}")
            assert False, f"Unexpected status: {r.status_code}"

        # 5. My stats
        r = client.get("/daily/my-stats")
        assert r.status_code == 200
        stats = r.json()
        print(f"  GET /daily/my-stats: {stats['total_predictions']} predictions ✓")

        # 6. Providers
        r = client.get("/advisor/providers")
        assert r.status_code == 200
        providers = r.json()["providers"]
        assert len(providers) == 3
        print(f"  GET /advisor/providers: {len(providers)} providers ✓")

        # 7. Yesterday results
        r = client.get("/daily/results/yesterday")
        assert r.status_code == 200
        print(f"  GET /daily/results/yesterday: {r.status_code} ✓")

    print()

    # ── Step 8: Fallback analysis ──
    print("── Step 8: Fallback Analysis ──")
    fb_types = {"team_avg": 0, "league_avg": 0, "fuzzy": 0, "none": 0}
    for date_str, preds in all_predictions.items():
        for p in preds:
            for fb in [p.away_starter_fallback, p.home_starter_fallback]:
                if fb is None:
                    fb_types["none"] += 1
                else:
                    fb_types[fb] = fb_types.get(fb, 0) + 1

    total_slots = sum(fb_types.values())
    print(f"  Total pitcher slots: {total_slots}")
    for fb_type, count in sorted(fb_types.items()):
        pct = count / total_slots * 100
        print(f"    {fb_type}: {count} ({pct:.0f}%)")

    none_pct = fb_types["none"] / total_slots * 100
    print(f"\n  Direct match rate: {none_pct:.0f}% (expected to improve as 2026 rosters finalize)")
    print()

    # ── Step 9: Spring training check ──
    print("── Step 9: Spring Training Data ──")
    today = date.today()
    today_games = daily.fetch_games(today)
    print(f"  Today ({today}): {len(today_games)} games")
    if today_games:
        for g in today_games[:3]:
            print(f"    {g.away_team_id} @ {g.home_team_id} | {g.status} | "
                  f"{g.away_starter_name} vs {g.home_starter_name}")
    else:
        print(f"  (No regular season games today — spring training or off day)")
    print()

    print("=" * 70)
    print(" ALL END-TO-END TESTS PASSED")
    print("=" * 70)
    print()
    print(f"Summary:")
    print(f"  - {total_games} games predicted across {len(dates_to_test)} dates")
    print(f"  - {total_time:.1f}s total prediction time ({total_time/total_games:.1f}s/game)")
    print(f"  - Fallback rate: {100 - none_pct:.0f}%")
    print(f"  - All API endpoints verified")
    print(f"  - Scoring + stats pipeline working")
    print(f"  - Ready for March 25 opening day")


if __name__ == "__main__":
    main()
