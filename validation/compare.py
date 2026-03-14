"""버전 간 검증 결과 비교."""

from __future__ import annotations

import json
import logging
from io import StringIO
from pathlib import Path

logger = logging.getLogger(__name__)


def compare_versions(
    output_dir: str = "output/validation/",
) -> str:
    """metrics_history.json에서 모든 버전의 결과를 비교하는 테이블 생성."""
    history_path = Path(output_dir) / "metrics_history.json"
    if not history_path.exists():
        return "No history found."

    with open(history_path) as f:
        history = json.load(f)

    if len(history) < 1:
        return "No results in history."

    buf = StringIO()
    w = buf.write

    w(f"{'Version':<10s}")

    metrics = [
        ("L1.k_rmse", "l1", "k_rmse"),
        ("L1.woba_r", "l1", "woba_corr"),
        ("L2.r_corr", "l2", "runs_corr"),
        ("L2.r_rmse", "l2", "runs_rmse"),
        ("L3.brier", "l3", "brier_score"),
        ("L3.auc", "l3", "auc_roc"),
        ("L4.w_rmse", "l4", "wins_rmse"),
        ("L4.w_corr", "l4", "wins_corr"),
    ]

    for label, _, _ in metrics:
        w(f"  {label:>9s}")
    w("\n")
    w("─" * (10 + len(metrics) * 11) + "\n")

    for entry in history:
        version = entry.get("version", "?")
        w(f"{version:<10s}")
        for _, level, metric in metrics:
            val = entry.get(level, {}).get(metric)
            if val is not None:
                w(f"  {val:9.4f}")
            else:
                w(f"  {'—':>9s}")
        w("\n")

    return buf.getvalue()
