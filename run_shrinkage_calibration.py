"""Phase 1-A 수축 보정: 그리드 서치 + 시간 분할 검증 + 전체 재검증 + 리포트."""

import logging
import time
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

from data.pipeline import DugoutDataPipeline
from simulation.game_level import run_game_level_simulation
from simulation.shrinkage import (
    apply_shrinkage,
    compute_metrics,
    grid_search_shrinkage,
)
from validation.l3_game import _compute_auc, _compute_calibration
from validation.ground_truth import load_actual_results

# ── 1. 데이터 로드 + 시뮬레이션 ──
pipeline = DugoutDataPipeline(season=2024)
data = pipeline.load_all()

t0 = time.time()
results = run_game_level_simulation(data, season=2024, n_sims=200, seed=42)
sim_time = time.time() - t0
logger.info("Simulation done: %.1fs", sim_time)

games = results.games

# ── 2. 시간 분할: 전반부 (3월~6월) / 후반부 (7월~9월) ──
first_half = [g for g in games if g.date[:7] <= "2024-06"]
second_half = [g for g in games if g.date[:7] >= "2024-07"]
logger.info("Temporal split: first_half=%d, second_half=%d", len(first_half), len(second_half))

# ── 3. 그리드 서치 (전반부에서 튜닝) ──
shrink_values = [round(0.50 + 0.05 * i, 2) for i in range(11)]  # 0.50 ~ 1.00

print("=" * 60)
print(" Task 2: Grid Search — Temporal Split Validation")
print("=" * 60)
print()

# 전반부 그리드 서치
print("── First Half (Mar-Jun) — In-Sample Tuning ──")
print(f"  Games: {len(first_half)}")
first_half_results = grid_search_shrinkage(first_half, shrink_values)

print(f"  {'shrink':>6s}  {'Brier':>7s}  {'LogLoss':>8s}  {'AUC':>6s}  {'N':>5s}")
for r in first_half_results:
    print(f"  {r['shrink']:6.2f}  {r['brier']:7.4f}  {r['log_loss']:8.4f}  {r['auc']:6.4f}  {r['n']:5.0f}")

# 최적 shrink (Brier 최소)
best_first = min(first_half_results, key=lambda x: x["brier"])
optimal_shrink = best_first["shrink"]
print(f"\n  Optimal shrink (min Brier on first half): {optimal_shrink}")
print()

# ── 4. 후반부 검증 (out-of-sample) ──
print("── Second Half (Jul-Sep) — Out-of-Sample Validation ──")
print(f"  Games: {len(second_half)}")
second_half_results = grid_search_shrinkage(second_half, shrink_values)

print(f"  {'shrink':>6s}  {'Brier':>7s}  {'LogLoss':>8s}  {'AUC':>6s}  {'N':>5s}")
for r in second_half_results:
    print(f"  {r['shrink']:6.2f}  {r['brier']:7.4f}  {r['log_loss']:8.4f}  {r['auc']:6.4f}  {r['n']:5.0f}")

# 후반부에서 optimal_shrink 적용 결과
oos_result = next(r for r in second_half_results if r["shrink"] == optimal_shrink)
raw_second = next(r for r in second_half_results if r["shrink"] == 1.0)

print(f"\n  Out-of-sample (shrink={optimal_shrink}):")
print(f"    Brier:    {raw_second['brier']:.4f} → {oos_result['brier']:.4f}  (Δ{oos_result['brier'] - raw_second['brier']:+.4f})")
print(f"    LogLoss:  {raw_second['log_loss']:.4f} → {oos_result['log_loss']:.4f}  (Δ{oos_result['log_loss'] - raw_second['log_loss']:+.4f})")
print(f"    AUC:      {raw_second['auc']:.4f} → {oos_result['auc']:.4f}  (Δ{oos_result['auc'] - raw_second['auc']:+.4f})")
print()

# ── 5. Task 3: 전체 시즌 L3 + L4 재검증 ──
print("=" * 60)
print(" Task 3: Full Season Re-Validation (Calibrated)")
print("=" * 60)
print()

# Raw (shrink=1.0) 메트릭
raw_metrics = compute_metrics(games)

# Calibrated 메트릭
calibrated_games = apply_shrinkage(games, optimal_shrink)
cal_metrics = compute_metrics(calibrated_games)

# Calibration buckets
def get_calibration(game_list):
    predictions, outcomes = [], []
    for g in game_list:
        if g.sim_away_win_pct is None or g.away_score is None or g.home_score is None:
            continue
        predictions.append(g.sim_away_win_pct)
        outcomes.append(1.0 if g.away_score > g.home_score else 0.0)
    return _compute_calibration(np.array(predictions), np.array(outcomes))

raw_cal = get_calibration(games)
cal_cal = get_calibration(calibrated_games)

print("── L3 Metrics: Phase 0 → 1-A Raw → 1-A Calibrated ──")
print(f"  Brier:    0.237 → {raw_metrics['brier']:.4f} → {cal_metrics['brier']:.4f}")
print(f"  LogLoss:  0.666 → {raw_metrics['log_loss']:.4f} → {cal_metrics['log_loss']:.4f}")
print(f"  AUC:      0.634 → {raw_metrics['auc']:.4f} → {cal_metrics['auc']:.4f}")
print(f"  Shrink:   n/a   → 1.00           → {optimal_shrink}")
print()

print("  Calibration (Raw → Calibrated):")
print(f"    {'Bucket':>10s}  {'Pred(raw)':>9s}  {'Pred(cal)':>9s}  {'Actual':>6s}  {'N':>5s}")
for label in sorted(raw_cal.keys()):
    rc = raw_cal[label]
    cc = cal_cal.get(label, {"pred_mean": 0, "actual_mean": 0, "n": 0})
    print(f"    {label:>10s}  {rc['pred_mean']:9.3f}  {cc['pred_mean']:9.3f}  {rc['actual_mean']:6.3f}  {rc['n']:5d}")
print()

# L4: 시즌 승수
print("── L4 Season Wins ──")
actual_results = load_actual_results(2024)


def compute_season_wins(game_list):
    team_wins_pred = defaultdict(float)
    for g in game_list:
        if g.sim_away_win_pct is None:
            continue
        team_wins_pred[g.away_team_id] += g.sim_away_win_pct
        team_wins_pred[g.home_team_id] += (1.0 - g.sim_away_win_pct)
    return team_wins_pred


raw_wins = compute_season_wins(games)
cal_wins = compute_season_wins(calibrated_games)

# RMSE 계산
def wins_rmse_and_corr(team_wins_pred):
    pred_list, actual_list = [], []
    for team_id in sorted(team_wins_pred.keys()):
        if team_id not in actual_results.team_actuals:
            continue
        pred_list.append(round(team_wins_pred[team_id]))
        actual_list.append(actual_results.team_actuals[team_id]["wins"])
    pred_arr = np.array(pred_list)
    actual_arr = np.array(actual_list)
    rmse = float(np.sqrt(np.mean((pred_arr - actual_arr) ** 2)))
    corr = float(np.corrcoef(pred_arr, actual_arr)[0, 1])
    return rmse, corr, pred_arr, actual_arr


raw_rmse, raw_corr, _, _ = wins_rmse_and_corr(raw_wins)
cal_rmse, cal_corr, cal_pred_arr, cal_actual_arr = wins_rmse_and_corr(cal_wins)

print(f"  Wins RMSE: 11.32 → {raw_rmse:.2f} → {cal_rmse:.2f}")
print(f"  Wins corr: 0.737 → {raw_corr:.4f} → {cal_corr:.4f}")
print()

# 팀별 비교
team_diffs = []
for team_id in sorted(cal_wins.keys()):
    if team_id not in actual_results.team_actuals:
        continue
    pred_w = round(cal_wins[team_id])
    actual_w = actual_results.team_actuals[team_id]["wins"]
    raw_pred_w = round(raw_wins[team_id])
    team_diffs.append({
        "team": team_id,
        "name": actual_results.team_actuals[team_id]["name"],
        "raw_pred": raw_pred_w,
        "cal_pred": pred_w,
        "actual": actual_w,
        "raw_diff": raw_pred_w - actual_w,
        "cal_diff": pred_w - actual_w,
    })

sorted_diffs = sorted(team_diffs, key=lambda x: abs(x["cal_diff"]), reverse=True)
print(f"  {'Team':>25s}  {'Raw':>5s}  {'Cal':>5s}  {'Actual':>6s}  {'RawΔ':>5s}  {'CalΔ':>5s}")
for t in sorted_diffs:
    print(f"  {t['name']:>25s}  {t['raw_pred']:5d}  {t['cal_pred']:5d}  {t['actual']:6d}  {t['raw_diff']:+5d}  {t['cal_diff']:+5d}")
print()

# ── 6. Task 4: 최종 리포트 + metrics_history.json ──
print("=" * 60)
print(" Task 4: Summary — Phase 1-A Shrinkage Calibration")
print("=" * 60)
print()
print(f"  Optimal shrink coefficient: {optimal_shrink}")
print(f"  Tuned on: first-half ({len(first_half)} games, Mar-Jun)")
print(f"  Validated on: second-half ({len(second_half)} games, Jul-Sep)")
print()

# Gate 판단
auc_vs_phase0 = cal_metrics["auc"] - 0.634
print("── Gate Assessment ──")
print(f"  Phase 0 AUC:        0.634")
print(f"  1-A Raw AUC:        {raw_metrics['auc']:.4f}")
print(f"  1-A Calibrated AUC: {cal_metrics['auc']:.4f}")
print(f"  AUC Δ vs Phase 0:   {auc_vs_phase0:+.4f}")
print()

if auc_vs_phase0 >= 0.02:
    print("  → AUC Δ ≥ 0.02: 선발투수 반영만으로 충분, Phase 1-B로 진행 가능")
elif auc_vs_phase0 >= 0.01:
    print("  → AUC Δ ≥ 0.01: 중간 구간, 추가 분석 후 판단")
elif auc_vs_phase0 >= 0:
    print("  → AUC Δ > 0 but < 0.01: Phase 0 수준 복원은 됐으나 개선폭 부족, Level 2 필요")
else:
    print("  → AUC Δ < 0: Phase 0보다 악화, 다른 접근 필요")

print()
print(f"  Brier improvement vs Phase 0: 0.237 → {cal_metrics['brier']:.4f} (Δ{cal_metrics['brier'] - 0.237:+.4f})")
print(f"  L4 RMSE improvement vs Phase 0: 11.32 → {cal_rmse:.2f} (Δ{cal_rmse - 11.32:+.2f})")
print()

# metrics_history.json 저장
metrics_history_path = Path("metrics_history.json")
if metrics_history_path.exists():
    with open(metrics_history_path) as f:
        history = json.load(f)
else:
    history = []

history.append({
    "version": "v1.0-A-calibrated",
    "description": "Phase 1-A with logistic shrinkage calibration",
    "shrink": optimal_shrink,
    "l3": {
        "brier": round(cal_metrics["brier"], 4),
        "log_loss": round(cal_metrics["log_loss"], 4),
        "auc": round(cal_metrics["auc"], 4),
        "n": int(cal_metrics["n"]),
    },
    "l4": {
        "wins_rmse": round(cal_rmse, 2),
        "wins_corr": round(cal_corr, 4),
    },
    "temporal_validation": {
        "first_half_n": len(first_half),
        "second_half_n": len(second_half),
        "oos_brier": round(oos_result["brier"], 4),
        "oos_log_loss": round(oos_result["log_loss"], 4),
        "oos_auc": round(oos_result["auc"], 4),
    },
    "comparison": {
        "phase0_auc": 0.634,
        "phase0_brier": 0.237,
        "phase0_l4_rmse": 11.32,
        "raw_1a_auc": round(raw_metrics["auc"], 4),
        "raw_1a_brier": round(raw_metrics["brier"], 4),
        "raw_1a_l4_rmse": round(raw_rmse, 2),
    },
})

with open(metrics_history_path, "w") as f:
    json.dump(history, f, indent=2)

print(f"  metrics_history.json updated with v1.0-A-calibrated")
print()
print("Done.")
