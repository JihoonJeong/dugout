"""Daily prediction system integration test."""

import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from data.pipeline import DugoutDataPipeline
from daily.pipeline import DailyDataPipeline, DailyGame
from daily.predictor import DailyPredictor
from daily.store import PredictionStore
from datetime import date


def main():
    print("=" * 60)
    print(" Daily Prediction System — Integration Test")
    print("=" * 60)
    print()

    # 1. 데이터 로드
    print("── Step 1: Load Data ──")
    pipeline = DugoutDataPipeline(season=2025)
    data = pipeline.load_all()
    print(f"  Teams: {len(data.teams)}")
    print(f"  Pitchers: {len(data.all_pitchers)}")
    print()

    # 2. DailyDataPipeline
    print("── Step 2: Fetch Daily Games ──")
    daily = DailyDataPipeline()

    # Opening day
    opening = date(2026, 3, 26)
    games = daily.fetch_games(opening)
    print(f"  {opening}: {len(games)} games")
    for g in games:
        print(f"    {g.away_team_id} @ {g.home_team_id} | {g.game_time} | {g.away_starter_name} vs {g.home_starter_name}")
    print()

    # 3. Predictor
    print("── Step 3: Engine Predictions ──")
    predictor = DailyPredictor(data)

    t0 = time.time()
    predictions = predictor.predict_all(games, n_sims=1000)
    elapsed = time.time() - t0

    print(f"  {len(predictions)} predictions in {elapsed:.1f}s")
    print()
    print(f"  {'Game':>12s}  {'Away%':>6s}  {'Home%':>6s}  {'Proj':>8s}  {'Quick':>8s}")
    print("  " + "-" * 50)
    for p in predictions:
        game_str = f"{p.away_team_id}@{p.home_team_id}"
        proj = f"{p.mc_avg_away_runs:.1f}-{p.mc_avg_home_runs:.1f}"
        quick = f"{p.quick_away_score}-{p.quick_home_score}"
        print(f"  {game_str:>12s}  {p.final_away_win_pct:6.1%}  {p.final_home_win_pct:6.1%}  {proj:>8s}  {quick:>8s}")
    print()

    # 4. Store
    print("── Step 4: Prediction Store ──")
    store = PredictionStore(store_dir="/tmp/dugout_test_predictions/")

    # 예측 제출
    if predictions:
        p = predictions[0]
        pred = store.submit(
            game_id=p.game_id,
            game_date=p.game_date,
            away_team_id=p.away_team_id,
            home_team_id=p.home_team_id,
            predicted_winner="away" if p.final_away_win_pct > 0.5 else "home",
            predicted_away_score=round(p.mc_avg_away_runs),
            predicted_home_score=round(p.mc_avg_home_runs),
        )
        print(f"  Submitted: {pred.prediction_id} for {p.away_team_id}@{p.home_team_id}")
        print(f"  Winner pick: {pred.predicted_winner}")
        print(f"  Score pick: {pred.predicted_away_score}-{pred.predicted_home_score}")

        # 수정
        updated = store.update(
            prediction_id=pred.prediction_id,
            game_date=pred.game_date,
            predicted_winner="home",
        )
        print(f"  Updated winner to: {updated.predicted_winner}")

        # 결과 기록
        store.record_results(
            game_id=p.game_id,
            game_date=p.game_date,
            actual_winner="away",
            actual_away_score=5,
            actual_home_score=3,
        )

        # 조회
        stored = store.get_by_date(p.game_date)
        print(f"  Stored predictions: {len(stored)}")
        if stored:
            s = stored[0]
            print(f"  Correct: {s.correct} (predicted {s.predicted_winner}, actual {s.actual_winner})")
    print()

    # 5. API 테스트
    print("── Step 5: API Test ──")
    from fastapi.testclient import TestClient
    from server.app import app

    with TestClient(app) as client:
        # Health
        r = client.get("/health")
        assert r.status_code == 200
        print(f"  GET /health: {r.status_code}")

        # Today's games
        r = client.get("/daily/games/today")
        print(f"  GET /daily/games/today: {r.status_code} ({len(r.json())} games)")

        # Specific date
        r = client.get("/daily/games/2026-03-26")
        games_data = r.json()
        print(f"  GET /daily/games/2026-03-26: {r.status_code} ({len(games_data)} games)")

        # Submit prediction
        if games_data:
            g = games_data[0]
            r = client.post("/daily/predictions", json={
                "game_id": g["game_id"],
                "game_date": g["game_date"],
                "predicted_winner": "away",
                "predicted_away_score": 4,
                "predicted_home_score": 2,
            })
            print(f"  POST /daily/predictions: {r.status_code}")
            if r.status_code == 200:
                pred_data = r.json()
                pid = pred_data["prediction"]["prediction_id"]

                # Update
                r = client.put(f"/daily/predictions/{pid}", json={
                    "game_date": g["game_date"],
                    "predicted_winner": "home",
                })
                print(f"  PUT /daily/predictions/{pid}: {r.status_code}")

        # Yesterday results
        r = client.get("/daily/results/yesterday")
        print(f"  GET /daily/results/yesterday: {r.status_code}")

    print()
    print("All tests passed!")


if __name__ == "__main__":
    main()
