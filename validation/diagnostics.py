"""검증 진단 — 편향/잔차/수렴 분석."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from .runner import ValidationResult

logger = logging.getLogger(__name__)


@dataclass
class DiagnosticReport:
    l1_bias: dict[str, float] | None = None
    l1_residuals: dict[str, list[float]] | None = None
    l2_bias_direction: str | None = None
    l3_calibration_gap: float | None = None
    issues: list[str] | None = None


def run_diagnostics(result: ValidationResult) -> DiagnosticReport:
    """검증 결과에서 체계적 편향과 문제점 진단."""
    diag = DiagnosticReport(issues=[])

    if result.l1:
        _diagnose_l1(result, diag)
    if result.l2:
        _diagnose_l2(result, diag)
    if result.l3:
        _diagnose_l3(result, diag)

    return diag


def _diagnose_l1(result: ValidationResult, diag: DiagnosticReport) -> None:
    """L1 편향 분석: 예측이 체계적으로 한쪽으로 치우쳐 있는지."""
    details = result.l1.player_details
    if not details:
        return

    biases = {}
    residuals = {}
    for metric in ["k", "bb", "hr", "woba"]:
        pred_key = f"pred_{metric}"
        actual_key = f"actual_{metric}"
        diffs = [d[pred_key] - d[actual_key] for d in details if pred_key in d and actual_key in d]
        if diffs:
            biases[metric] = float(np.mean(diffs))
            residuals[metric] = diffs

    diag.l1_bias = biases
    diag.l1_residuals = residuals

    # 체계적 편향 경고
    for metric, bias in biases.items():
        if abs(bias) > 0.01:
            diag.issues.append(
                f"L1 systematic bias in {metric}: {bias:+.4f} "
                f"(model {'over' if bias > 0 else 'under'}-predicts)"
            )

    # IBB 이슈 탐지
    ibb_suspects = [
        d for d in details
        if "actual_bb_no_ibb" in d
        and d["actual_bb_no_ibb"] > 0
        and abs(d["pred_bb"] - d["actual_bb_no_ibb"]) < abs(d["pred_bb"] - d["actual_bb"]) * 0.5
    ]
    if len(ibb_suspects) > 5:
        diag.issues.append(
            f"L1: {len(ibb_suspects)} players have BB% error halved when excluding IBB — "
            "IBB may be inflating actual BB rates"
        )


def _diagnose_l2(result: ValidationResult, diag: DiagnosticReport) -> None:
    """L2 편향 분석: 시뮬레이션 득점 과대/과소."""
    bias = result.l2.scoring_bias
    diag.l2_bias_direction = "over" if bias > 0 else "under"
    if abs(bias) > 0.3:
        diag.issues.append(
            f"L2 scoring bias: {bias:+.2f} R/G — simulation systematically "
            f"{'over' if bias > 0 else 'under'}-scores"
        )


def _diagnose_l3(result: ValidationResult, diag: DiagnosticReport) -> None:
    """L3 칼리브레이션 분석."""
    cal = result.l3.calibration
    if not cal:
        return

    gaps = []
    for label, bucket in cal.items():
        gap = abs(bucket["pred_mean"] - bucket["actual_mean"])
        gaps.append(gap)

    avg_gap = float(np.mean(gaps)) if gaps else 0.0
    diag.l3_calibration_gap = avg_gap

    if avg_gap > 0.05:
        diag.issues.append(
            f"L3 calibration gap: avg {avg_gap:.3f} — predictions may be poorly calibrated"
        )
