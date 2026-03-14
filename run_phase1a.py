"""Phase 1-A: 경기별 선발투수 반영 시뮬레이션 + 검증."""

import logging
import time

import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

from data.pipeline import DugoutDataPipeline
from simulation.game_level import run_game_level_simulation
from validation.starter_impact import analyze_starter_impact, format_starter_impact
from validation.l3_game import _compute_auc, _compute_calibration

logger = logging.getLogger(__name__)

# ── 1. 데이터 로드 ──
pipeline = DugoutDataPipeline(season=2024)
data = pipeline.load_all()

# ── 2. 경기별 시뮬레이션 (n_sims=1000) ──
t0 = time.time()
results = run_game_level_simulation(data, season=2024, n_sims=200, seed=42)
sim_time = time.time() - t0

# ── 3. L3 메트릭 산출 ──
predictions = []
outcomes = []
for g in results.games:
    if g.sim_away_win_pct is None or g.away_score is None or g.home_score is None:
        continue
    predictions.append(g.sim_away_win_pct)
    actual = 1.0 if g.away_score > g.home_score else 0.0
    outcomes.append(actual)

pred = np.array(predictions)
actual = np.array(outcomes)

# Brier
brier = float(np.mean((pred - actual) ** 2))

# Log Loss
eps = 1e-15
pred_clipped = np.clip(pred, eps, 1 - eps)
ll = -float(np.mean(actual * np.log(pred_clipped) + (1 - actual) * np.log(1 - pred_clipped)))

# AUC
auc = _compute_auc(pred, actual)

# Calibration
cal = _compute_calibration(pred, actual)

# ── 4. L4 시즌 승수 ──
from collections import defaultdict
team_wins_pred = defaultdict(float)
team_games = defaultdict(int)

for g in results.games:
    if g.sim_away_win_pct is None:
        continue
    team_wins_pred[g.away_team_id] += g.sim_away_win_pct
    team_wins_pred[g.home_team_id] += (1.0 - g.sim_away_win_pct)
    team_games[g.away_team_id] += 1
    team_games[g.home_team_id] += 1

# 실제 승수
from validation.ground_truth import load_actual_results
actual_results = load_actual_results(2024)

pred_wins_list = []
actual_wins_list = []
team_diffs = []

for team_id in sorted(team_wins_pred.keys()):
    if team_id not in actual_results.team_actuals:
        continue
    pred_w = round(team_wins_pred[team_id])
    actual_w = actual_results.team_actuals[team_id]["wins"]
    pred_wins_list.append(pred_w)
    actual_wins_list.append(actual_w)
    team_diffs.append({
        "team": team_id,
        "name": actual_results.team_actuals[team_id]["name"],
        "pred": pred_w,
        "actual": actual_w,
        "diff": pred_w - actual_w,
    })

pred_arr = np.array(pred_wins_list)
actual_arr = np.array(actual_wins_list)
wins_rmse = float(np.sqrt(np.mean((pred_arr - actual_arr) ** 2)))
wins_corr = float(np.corrcoef(pred_arr, actual_arr)[0, 1])

# ── 5. Starter Impact ──
impact = analyze_starter_impact(results)

# ── 6. 리포트 출력 ──
print("=" * 60)
print(" Phase 1-A: Game-Level Starting Pitcher Simulation")
print("=" * 60)
print()
print(f"  Games simulated: {results.n_valid}")
print(f"  Sims per game: {results.n_sims_per_game}")
print(f"  Total sim time: {sim_time:.1f}s")
print(f"  Skipped: {results.n_skipped}")
print(f"  Fallback rate: {results.fallback_rate:.1%}")
print(f"  Fallback breakdown: {results.fallback_stats}")
print()

print("── L3 Comparison (Phase 0 → Phase 1-A) ──")
print(f"  Brier:    0.237 → {brier:.4f}  (threshold < 0.235)")
print(f"  Log Loss: 0.666 → {ll:.4f}  (threshold < 0.665)")
print(f"  AUC:      0.634 → {auc:.4f}  (threshold > 0.65)")
print(f"  AUC delta: {auc - 0.634:+.4f}")
print()

print("  Calibration:")
print(f"    {'Bucket':>10s}  {'Pred':>6s}  {'Actual':>6s}  {'N':>5s}")
for label, c in sorted(cal.items()):
    print(f"    {label:>10s}  {c['pred_mean']:6.3f}  {c['actual_mean']:6.3f}  {c['n']:5d}")
print()

print("── L4 Season Wins ──")
print(f"  Wins RMSE: 11.32 → {wins_rmse:.2f}  (threshold < 10.0)")
print(f"  Wins corr: 0.737 → {wins_corr:.4f}")
print()

sorted_diffs = sorted(team_diffs, key=lambda x: x["diff"])
print("  Teams (sorted by diff):")
print(f"    {'Team':>25s}  {'Pred':>5s}  {'Actual':>6s}  {'Diff':>5s}")
for t in sorted_diffs:
    print(f"    {t['name']:>25s}  {t['pred']:5d}  {t['actual']:6d}  {t['diff']:+5d}")
print()

print(format_starter_impact(impact))

# ── Level 2 게이트 판단 ──
auc_delta = auc - 0.634
print("── Level 2 Gate ──")
if auc_delta < 0.01:
    print(f"  AUC delta = {auc_delta:+.4f} < 0.01 → 선발투수만으로는 부족, Level 2 (platoon lineup) 필요")
elif auc_delta > 0.02:
    print(f"  AUC delta = {auc_delta:+.4f} > 0.02 → 선발투수만으로 충분, 1-B로 진행")
else:
    print(f"  AUC delta = {auc_delta:+.4f} → 중간 구간, starter impact spread를 보고 판단 필요")
    print(f"  Mean win% spread: {impact.mean_win_pct_spread:.4f}")
