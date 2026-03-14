"""경기 결과에서 하이라이트 추출."""

from __future__ import annotations

from engine.models import GameResult


def extract_highlights(result: GameResult, away_id: str, home_id: str) -> list[str]:
    """경기 결과에서 주요 장면을 추출."""
    highlights = []

    # 최종 스코어
    highlights.append(
        f"Final: {away_id} {result.score['away']}, {home_id} {result.score['home']}"
    )

    # 홈런 수집
    for play in result.play_log:
        if play.event == "HR":
            side = away_id if play.batter in [b for b in _get_side_ids(result, "away")] else home_id
            runs = play.runs_scored
            if runs >= 2:
                highlights.append(f"{play.description} ({runs}-run HR)")
            else:
                highlights.append(f"{play.description} (solo HR)")

    # 리드 변경 수집
    away_runs = 0
    home_runs = 0
    prev_leader = None
    for play in result.play_log:
        if play.runs_scored > 0:
            if play.half == "top":
                away_runs += play.runs_scored
            else:
                home_runs += play.runs_scored

            leader = None
            if away_runs > home_runs:
                leader = "away"
            elif home_runs > away_runs:
                leader = "home"

            if leader != prev_leader and leader is not None and prev_leader is not None:
                lead_team = away_id if leader == "away" else home_id
                highlights.append(f"{lead_team} takes the lead {away_runs}-{home_runs}")
            prev_leader = leader

    # 연장전
    if result.innings_played > 9:
        highlights.append(f"Extra innings: {result.innings_played} innings")

    return highlights[:10]  # 최대 10개


def _get_side_ids(result: GameResult, side: str) -> set:
    """해당 사이드의 타자 ID 추출."""
    ids = set()
    for play in result.play_log:
        if play.half == ("top" if side == "away" else "bottom"):
            ids.add(play.batter)
    return ids
