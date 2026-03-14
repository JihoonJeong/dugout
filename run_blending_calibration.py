"""Phase 1-A 블렌딩 보정: Phase 0 baseline + 블렌딩 + 그리드 서치 + 검증."""

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

from data.constants import TEAM_MAPPING
from data.pipeline import DugoutDataPipeline
from data.schedule import fetch_season_schedule
from engine.monte_carlo import simulate_series
from engine.models import ParkFactors
from simulation.game_level import run_game_level_simulation
from simulation.blending import apply_blending, grid_search_blending
from simulation.shrinkage import compute_metrics, shrink_probability
from validation.l3_game import _compute_calibration
from validation.ground_truth import load_actual_results

# ── 1. 데이터 로드 ──
pipeline = DugoutDataPipeline(season=2024)
data = pipeline.load_all()

# ── 2. Phase 0 baseline: 고정 선발로 2430 경기 시뮬레이션 ──
logger.info("Running Phase 0 baseline (fixed starters) for all games...")
schedule = fetch_season_schedule(2024, cache_dir="cache/")
rng = np.random.default_rng(42)

phase0_games = []
t0 = time.time()

for i, game in enumerate(schedule):
    if game.away_team_id not in data.teams or game.home_team_id not in data.teams:
        continue

    away_team = data.teams[game.away_team_id]
    home_team = data.teams[game.home_team_id]

    park_name = TEAM_MAPPING[game.home_team_id]["park"]
    park = data.parks.get(park_name)
    if park is None:
        park = ParkFactors(park_name=park_name, pf_1b=100, pf_2b=100, pf_3b=100, pf_hr=100)

    game_seed = int(rng.integers(1_000_000_000))
    series = simulate_series(away_team, home_team, park, data.league,
                             n_simulations=200, seed=game_seed)

    from dataclasses import replace
    p0_game = replace(game, sim_away_win_pct=series.away_win_pct,
                      sim_avg_away_runs=series.avg_away_runs,
                      sim_avg_home_runs=series.avg_home_runs)
    phase0_games.append(p0_game)

    if (i + 1) % 500 == 0:
        elapsed = time.time() - t0
        logger.info("  Phase 0: %d/%d games (%.1fs)", i + 1, len(schedule), elapsed)

p0_time = time.time() - t0
logger.info("Phase 0 baseline done: %d games in %.1fs", len(phase0_games), p0_time)

# ── 3. Phase 1-A: 경기별 선발 시뮬레이션 ──
logger.info("Running Phase 1-A (game-level starters)...")
t0 = time.time()
results_1a = run_game_level_simulation(data, season=2024, n_sims=200, seed=42)
p1a_time = time.time() - t0
logger.info("Phase 1-A done: %.1fs", p1a_time)

phase1a_games = results_1a.games

# ── 4. 시간 분할 ──
p0_first = [g for g in phase0_games if g.date[:7] <= "2024-06"]
p0_second = [g for g in phase0_games if g.date[:7] >= "2024-07"]
p1a_first = [g for g in phase1a_games if g.date[:7] <= "2024-06"]
p1a_second = [g for g in phase1a_games if g.date[:7] >= "2024-07"]

logger.info("Temporal split: first=%d/%d, second=%d/%d",
            len(p0_first), len(p1a_first), len(p0_second), len(p1a_second))

# ── 5. Alpha 그리드 서치 (전반부, AUC 기준) ──
SHRINK = 0.60
alpha_values = [round(0.30 + 0.05 * i, 2) for i in range(9)]  # 0.30 ~ 0.70

print("=" * 60)
print(" Task 2: Alpha Grid Search — Temporal Split Validation")
print("=" * 60)
print()

# 전반부 튜닝
print("── First Half (Mar-Jun) — In-Sample Tuning ──")
print(f"  Games: {len(p1a_first)}, shrink={SHRINK} fixed")
first_results = grid_search_blending(p0_first, p1a_first, alpha_values, shrink=SHRINK)

print(f"  {'alpha':>6s}  {'Brier':>7s}  {'LogLoss':>8s}  {'AUC':>6s}  {'N':>5s}")
for r in first_results:
    print(f"  {r['alpha']:6.2f}  {r['brier']:7.4f}  {r['log_loss']:8.4f}  {r['auc']:6.4f}  {r['n']:5.0f}")

# 최적 alpha (AUC 최대)
best_first = max(first_results, key=lambda x: x["auc"])
optimal_alpha = best_first["alpha"]
print(f"\n  Optimal alpha (max AUC on first half): {optimal_alpha}")
print()

# ── 6. 후반부 검증 (out-of-sample) ──
print("── Second Half (Jul-Sep) — Out-of-Sample Validation ──")
print(f"  Games: {len(p1a_second)}, shrink={SHRINK}, alpha={optimal_alpha}")
second_results = grid_search_blending(p0_second, p1a_second, alpha_values, shrink=SHRINK)

print(f"  {'alpha':>6s}  {'Brier':>7s}  {'LogLoss':>8s}  {'AUC':>6s}  {'N':>5s}")
for r in second_results:
    print(f"  {r['alpha']:6.2f}  {r['brier']:7.4f}  {r['log_loss']:8.4f}  {r['auc']:6.4f}  {r['n']:5.0f}")

oos_result = next(r for r in second_results if r["alpha"] == optimal_alpha)
# raw 1-A (alpha=0, no shrink) for comparison
raw_1a_second = compute_metrics(p1a_second)

print(f"\n  Out-of-sample (alpha={optimal_alpha}, shrink={SHRINK}):")
print(f"    Brier:    {raw_1a_second['brier']:.4f} → {oos_result['brier']:.4f}")
print(f"    LogLoss:  {raw_1a_second['log_loss']:.4f} → {oos_result['log_loss']:.4f}")
print(f"    AUC:      {raw_1a_second['auc']:.4f} → {oos_result['auc']:.4f}")
print()

# ── 7. Task 3: 전체 시즌 L3 + L4 재검증 ──
print("=" * 60)
print(" Task 3: Full Season Re-Validation (Blended + Calibrated)")
print("=" * 60)
print()

# Raw 1-A
raw_metrics = compute_metrics(phase1a_games)

# Phase 0 only
p0_metrics = compute_metrics(phase0_games)

# Blended + calibrated
blended_games = apply_blending(phase0_games, phase1a_games, optimal_alpha, shrink=SHRINK)
bl_metrics = compute_metrics(blended_games)

# Calibration
def get_calibration(game_list):
    predictions, outcomes = [], []
    for g in game_list:
        if g.sim_away_win_pct is None or g.away_score is None or g.home_score is None:
            continue
        predictions.append(g.sim_away_win_pct)
        outcomes.append(1.0 if g.away_score > g.home_score else 0.0)
    return _compute_calibration(np.array(predictions), np.array(outcomes))

raw_cal = get_calibration(phase1a_games)
bl_cal = get_calibration(blended_games)

print("── L3 Metrics: Phase 0 → 1-A Raw → 1-A Blended+Cal ──")
print(f"  Brier:    {p0_metrics['brier']:.4f} → {raw_metrics['brier']:.4f} → {bl_metrics['brier']:.4f}")
print(f"  LogLoss:  {p0_metrics['log_loss']:.4f} → {raw_metrics['log_loss']:.4f} → {bl_metrics['log_loss']:.4f}")
print(f"  AUC:      {p0_metrics['auc']:.4f} → {raw_metrics['auc']:.4f} → {bl_metrics['auc']:.4f}")
print(f"  Alpha:    n/a    → n/a    → {optimal_alpha}")
print(f"  Shrink:   n/a    → n/a    → {SHRINK}")
print()

print("  Calibration (Raw 1-A → Blended+Cal):")
print(f"    {'Bucket':>10s}  {'Pred(raw)':>9s}  {'Pred(bl)':>9s}  {'Actual':>6s}  {'N':>5s}")
for label in sorted(raw_cal.keys()):
    rc = raw_cal[label]
    bc = bl_cal.get(label, {"pred_mean": 0, "actual_mean": 0, "n": 0})
    print(f"    {label:>10s}  {rc['pred_mean']:9.3f}  {bc['pred_mean']:9.3f}  {rc['actual_mean']:6.3f}  {rc['n']:5d}")
print()

# L4
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
    return rmse, corr

p0_rmse, p0_corr = wins_rmse_and_corr(compute_season_wins(phase0_games))
raw_rmse, raw_corr = wins_rmse_and_corr(compute_season_wins(phase1a_games))
bl_rmse, bl_corr = wins_rmse_and_corr(compute_season_wins(blended_games))

print(f"  Wins RMSE: {p0_rmse:.2f} → {raw_rmse:.2f} → {bl_rmse:.2f}")
print(f"  Wins corr: {p0_corr:.4f} → {raw_corr:.4f} → {bl_corr:.4f}")
print()

# 팀별 비교
bl_wins = compute_season_wins(blended_games)
raw_wins = compute_season_wins(phase1a_games)
team_diffs = []
for team_id in sorted(bl_wins.keys()):
    if team_id not in actual_results.team_actuals:
        continue
    bl_pred = round(bl_wins[team_id])
    raw_pred = round(raw_wins[team_id])
    actual_w = actual_results.team_actuals[team_id]["wins"]
    team_diffs.append({
        "name": actual_results.team_actuals[team_id]["name"],
        "raw": raw_pred, "blended": bl_pred, "actual": actual_w,
        "raw_diff": raw_pred - actual_w, "bl_diff": bl_pred - actual_w,
    })

sorted_diffs = sorted(team_diffs, key=lambda x: abs(x["bl_diff"]), reverse=True)
print(f"  {'Team':>25s}  {'Raw':>5s}  {'Blend':>5s}  {'Actual':>6s}  {'RawΔ':>5s}  {'BlΔ':>5s}")
for t in sorted_diffs:
    print(f"  {t['name']:>25s}  {t['raw']:5d}  {t['blended']:5d}  {t['actual']:6d}  {t['raw_diff']:+5d}  {t['bl_diff']:+5d}")
print()

# ── 8. Task 4: 최종 리포트 + Gate Assessment ──
print("=" * 60)
print(" Task 4: Summary — Phase 1-A Blending + Calibration")
print("=" * 60)
print()
print(f"  Optimal alpha: {optimal_alpha}")
print(f"  Shrink: {SHRINK}")
print(f"  Tuned on: first-half ({len(p1a_first)} games, Mar-Jun)")
print(f"  Validated on: second-half ({len(p1a_second)} games, Jul-Sep)")
print()

auc_vs_phase0 = bl_metrics["auc"] - p0_metrics["auc"]
print("── Gate Assessment ──")
print(f"  Phase 0 AUC:           {p0_metrics['auc']:.4f}")
print(f"  1-A Raw AUC:           {raw_metrics['auc']:.4f}")
print(f"  1-A Blended+Cal AUC:   {bl_metrics['auc']:.4f}")
print(f"  AUC Δ vs Phase 0:      {auc_vs_phase0:+.4f}")
print()
print(f"  Phase 0 Brier:         {p0_metrics['brier']:.4f}")
print(f"  1-A Blended+Cal Brier: {bl_metrics['brier']:.4f}")
print(f"  Brier Δ vs Phase 0:    {bl_metrics['brier'] - p0_metrics['brier']:+.4f}")
print()
print(f"  Phase 0 L4 RMSE:       {p0_rmse:.2f}")
print(f"  1-A Blended+Cal RMSE:  {bl_rmse:.2f}")
print(f"  RMSE Δ vs Phase 0:     {bl_rmse - p0_rmse:+.2f}")
print()

if auc_vs_phase0 >= 0.02:
    gate = "AUC Δ ≥ 0.02: Phase 1-A 성공, 1-B로 진행"
elif auc_vs_phase0 >= 0.01:
    gate = "AUC Δ ≥ 0.01: 중간 구간, 추가 분석 필요"
elif auc_vs_phase0 >= 0:
    gate = "AUC Δ > 0: Phase 0 수준 복원, 개선폭은 부족 — Level 2 진입 권장"
else:
    gate = "AUC Δ < 0: Phase 0보다 악화, 다른 접근 필요"

if bl_rmse > 8.0:
    gate += "\n  ⚠ L4 RMSE > 8.0 — alpha가 너무 높을 수 있음"

print(f"  판단: {gate}")
print()

# metrics_history.json 업데이트
metrics_history_path = Path("metrics_history.json")
if metrics_history_path.exists():
    with open(metrics_history_path) as f:
        history = json.load(f)
else:
    history = []

history.append({
    "version": "v1.0-A-blended",
    "description": "Phase 1-A with team-starter blending + logistic shrinkage",
    "alpha": optimal_alpha,
    "shrink": SHRINK,
    "l3": {
        "brier": round(bl_metrics["brier"], 4),
        "log_loss": round(bl_metrics["log_loss"], 4),
        "auc": round(bl_metrics["auc"], 4),
        "n": int(bl_metrics["n"]),
    },
    "l4": {
        "wins_rmse": round(bl_rmse, 2),
        "wins_corr": round(bl_corr, 4),
    },
    "temporal_validation": {
        "first_half_n": len(p1a_first),
        "second_half_n": len(p1a_second),
        "oos_brier": round(oos_result["brier"], 4),
        "oos_log_loss": round(oos_result["log_loss"], 4),
        "oos_auc": round(oos_result["auc"], 4),
    },
    "comparison": {
        "phase0_auc": round(p0_metrics["auc"], 4),
        "phase0_brier": round(p0_metrics["brier"], 4),
        "phase0_l4_rmse": round(p0_rmse, 2),
        "raw_1a_auc": round(raw_metrics["auc"], 4),
        "raw_1a_brier": round(raw_metrics["brier"], 4),
        "raw_1a_l4_rmse": round(raw_rmse, 2),
    },
})

with open(metrics_history_path, "w") as f:
    json.dump(history, f, indent=2)

print(f"  metrics_history.json updated with v1.0-A-blended")
print()
print("Done.")
