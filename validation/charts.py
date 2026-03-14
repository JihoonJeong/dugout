"""검증 결과 차트 생성 (matplotlib)."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from .runner import ValidationResult

logger = logging.getLogger(__name__)


def generate_charts(result: ValidationResult, output_dir: str = "output/validation/") -> list[str]:
    """검증 결과 차트 생성. 생성된 파일 경로 리스트 반환."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib not installed — skipping charts")
        return []

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    created = []

    if result.l1:
        path = _chart_l1_woba(result, plt, out)
        if path:
            created.append(path)

    if result.l2:
        path = _chart_l2_runs(result, plt, out)
        if path:
            created.append(path)

    if result.l3:
        path = _chart_l3_calibration(result, plt, out)
        if path:
            created.append(path)

    if result.l4:
        path = _chart_l4_wins(result, plt, out)
        if path:
            created.append(path)

    return created


def _chart_l1_woba(result: ValidationResult, plt, out: Path) -> str | None:
    details = result.l1.player_details
    if not details:
        return None

    pred = [d["pred_woba"] for d in details]
    actual = [d["actual_woba"] for d in details]

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.scatter(actual, pred, alpha=0.4, s=15)
    lo = min(min(actual), min(pred)) - 0.02
    hi = max(max(actual), max(pred)) + 0.02
    ax.plot([lo, hi], [lo, hi], "r--", linewidth=1)
    ax.set_xlabel("Actual wOBA")
    ax.set_ylabel("Predicted wOBA")
    ax.set_title(f"L1: wOBA Predicted vs Actual (r={result.l1.woba_corr:.3f})")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_aspect("equal")

    path = str(out / f"l1_woba_{result.version}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def _chart_l2_runs(result: ValidationResult, plt, out: Path) -> str | None:
    details = result.l2.team_details
    if not details:
        return None

    names = [d["name"] for d in details]
    sim = [d["sim_rpg"] for d in details]
    actual = [d["actual_rpg"] for d in details]

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.scatter(actual, sim, alpha=0.7, s=40)
    for i, name in enumerate(names):
        ax.annotate(name, (actual[i], sim[i]), fontsize=6, alpha=0.7)
    lo = min(min(actual), min(sim)) - 0.2
    hi = max(max(actual), max(sim)) + 0.2
    ax.plot([lo, hi], [lo, hi], "r--", linewidth=1)
    ax.set_xlabel("Actual R/G")
    ax.set_ylabel("Simulated R/G")
    ax.set_title(f"L2: Team Scoring (r={result.l2.runs_corr:.3f}, bias={result.l2.scoring_bias:+.2f})")

    path = str(out / f"l2_runs_{result.version}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def _chart_l3_calibration(result: ValidationResult, plt, out: Path) -> str | None:
    cal = result.l3.calibration
    if not cal:
        return None

    pred_means = [v["pred_mean"] for v in cal.values()]
    actual_means = [v["actual_mean"] for v in cal.values()]

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.scatter(pred_means, actual_means, s=60, zorder=3)
    ax.plot([0, 1], [0, 1], "r--", linewidth=1)
    ax.set_xlabel("Predicted Win Probability")
    ax.set_ylabel("Actual Win Rate")
    ax.set_title(f"L3: Calibration (Brier={result.l3.brier_score:.4f})")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")

    path = str(out / f"l3_calibration_{result.version}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def _chart_l4_wins(result: ValidationResult, plt, out: Path) -> str | None:
    details = result.l4.team_details
    if not details:
        return None

    sorted_teams = sorted(details, key=lambda x: x["actual_wins"])
    names = [t["name"] for t in sorted_teams]
    actual = [t["actual_wins"] for t in sorted_teams]
    pred = [t["pred_wins"] for t in sorted_teams]
    pythag = [t["pythag_wins"] for t in sorted_teams]

    y = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(10, 12))
    ax.barh(y - 0.2, actual, 0.2, label="Actual", alpha=0.8)
    ax.barh(y, pred, 0.2, label="Predicted", alpha=0.8)
    ax.barh(y + 0.2, pythag, 0.2, label="Pythagorean", alpha=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=7)
    ax.set_xlabel("Wins")
    ax.set_title(f"L4: Season Wins (RMSE={result.l4.wins_rmse:.1f}, Pythag={result.l4.pythag_wins_rmse:.1f})")
    ax.legend()

    path = str(out / f"l4_wins_{result.version}.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path
