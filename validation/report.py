"""검증 결과 리포트 생성."""

from __future__ import annotations

import logging
from io import StringIO

from .runner import ValidationResult

logger = logging.getLogger(__name__)

PASS_MARK = "PASS"
FAIL_MARK = "FAIL"


def generate_report(result: ValidationResult) -> str:
    """텍스트 기반 검증 리포트 생성."""
    buf = StringIO()
    w = buf.write

    w(f"{'=' * 60}\n")
    w(f" Dugout Validation Report — {result.version} / {result.season}\n")
    w(f"{'=' * 60}\n\n")

    # Summary dashboard
    w("## Summary\n\n")
    summary = result.summary()
    total_pass = 0
    total_checks = 0
    for level, checks in summary.items():
        for metric, passed in checks.items():
            mark = PASS_MARK if passed else FAIL_MARK
            w(f"  [{mark}] {level}.{metric}\n")
            total_pass += int(passed)
            total_checks += 1
    w(f"\n  Total: {total_pass}/{total_checks} passed\n\n")

    # L1 Detail
    if result.l1:
        l1 = result.l1
        w(f"{'─' * 60}\n")
        w("## L1: Player Accuracy\n\n")
        w(f"  Batters evaluated: {l1.n_batters}\n")
        w(f"  K%  RMSE:  {l1.k_rmse:.4f}  (threshold < 0.040)\n")
        w(f"  BB% RMSE:  {l1.bb_rmse:.4f}  (threshold < 0.030)\n")
        w(f"  HR  RMSE:  {l1.hr_rmse:.4f}  (threshold < 0.015)\n")
        w(f"  wOBA RMSE: {l1.woba_rmse:.4f}  (threshold < 0.030)\n")
        w(f"  wOBA corr: {l1.woba_corr:.4f}  (threshold > 0.80)\n\n")

        if l1.league_avg_restoration:
            w("  League Avg Restoration (|weighted_avg - league_rate|):\n")
            for event, delta in l1.league_avg_restoration.items():
                w(f"    {event}: {delta:.4f}\n")
            w("\n")

        if l1.spot_checks:
            w("  Top wOBA discrepancy players:\n")
            for sc in l1.spot_checks[:5]:
                w(f"    {sc['name']:20s}  pred={sc['pred_woba']:.3f}  actual={sc['actual_woba']:.3f}"
                  f"  err={sc['woba_error']:+.3f}\n")
            w("\n")

    # L2 Detail
    if result.l2:
        l2 = result.l2
        w(f"{'─' * 60}\n")
        w("## L2: Team Scoring\n\n")
        w(f"  Teams evaluated: {l2.n_teams}\n")
        w(f"  Runs corr: {l2.runs_corr:.4f}  (threshold > 0.85)\n")
        w(f"  Runs RMSE: {l2.runs_rmse:.4f}  (threshold < 0.50)\n")
        w(f"  Mean sim R/G:    {l2.mean_sim_runs:.2f}\n")
        w(f"  Mean actual R/G: {l2.mean_actual_runs:.2f}\n")
        w(f"  Scoring bias:    {l2.scoring_bias:+.2f} R/G\n\n")

        # 상위/하위 5팀
        sorted_by_diff = sorted(l2.team_details, key=lambda x: x["diff"])
        w("  Most under-predicted (sim < actual):\n")
        for t in sorted_by_diff[:3]:
            w(f"    {t['name']:25s}  sim={t['sim_rpg']:.2f}  actual={t['actual_rpg']:.2f}  diff={t['diff']:+.2f}\n")
        w("  Most over-predicted (sim > actual):\n")
        for t in sorted_by_diff[-3:]:
            w(f"    {t['name']:25s}  sim={t['sim_rpg']:.2f}  actual={t['actual_rpg']:.2f}  diff={t['diff']:+.2f}\n")
        w("\n")

    # L3 Detail
    if result.l3:
        l3 = result.l3
        w(f"{'─' * 60}\n")
        w("## L3: Game Prediction\n\n")
        w(f"  Games evaluated: {l3.n_games}\n")
        w(f"  Brier Score: {l3.brier_score:.4f}  (threshold < 0.250)\n")
        w(f"  Log Loss:    {l3.log_loss:.4f}  (threshold < 0.695)\n")
        w(f"  AUC-ROC:     {l3.auc_roc:.4f}  (threshold > 0.55)\n\n")

        if l3.calibration:
            w("  Calibration buckets:\n")
            w(f"    {'Bucket':>10s}  {'Pred':>6s}  {'Actual':>6s}  {'N':>5s}\n")
            for label, cal in sorted(l3.calibration.items()):
                w(f"    {label:>10s}  {cal['pred_mean']:6.3f}  {cal['actual_mean']:6.3f}  {cal['n']:5d}\n")
            w("\n")

    # L4 Detail
    if result.l4:
        l4 = result.l4
        w(f"{'─' * 60}\n")
        w("## L4: Season Prediction\n\n")
        w(f"  Teams evaluated: {l4.n_teams}\n")
        w(f"  Wins RMSE:       {l4.wins_rmse:.2f}  (threshold < 8.0, PECOTA/ZiPS range: 7-10)\n")
        w(f"  Wins corr:       {l4.wins_corr:.4f}  (threshold > 0.75)\n")
        w(f"  Playoff correct: {l4.playoff_correct}/{l4.playoff_total}\n")
        w(f"  Pythag RMSE (actual R):   {l4.pythag_wins_rmse:.2f}  (baseline, uses actual runs)\n")
        w(f"  Pythag RMSE (sim R):      {l4.sim_pythag_wins_rmse:.2f}  (engine runs → pythagorean)\n")
        w(f"  Sim Pythag vs Direct:     {l4.sim_pythag_vs_direct_rmse:.2f}  (internal consistency)\n\n")

        sorted_by_diff = sorted(l4.team_details, key=lambda x: x["diff"])
        w("  Team predictions (sorted by diff):\n")
        w(f"    {'Team':>25s}  {'Pred':>5s}  {'Actual':>6s}  {'Pythag':>6s}  {'SimPyth':>7s}  {'Diff':>5s}\n")
        for t in sorted_by_diff:
            w(f"    {t['name']:>25s}  {t['pred_wins']:5d}  {t['actual_wins']:6d}  {t['pythag_wins']:6d}  {t.get('sim_pythag_wins', 0):7d}  {t['diff']:+5d}\n")
        w("\n")

    # Timing
    w(f"{'─' * 60}\n")
    w("## Timing\n\n")
    for step, elapsed in result.elapsed_seconds.items():
        w(f"  {step}: {elapsed:.1f}s\n")
    w("\n")

    w(f"{'=' * 60}\n")

    return buf.getvalue()
