"""매치업 분석 프롬프트 템플릿."""

from __future__ import annotations

from .base import MatchupContext

SYSTEM_PROMPT = """You are an expert MLB analyst and prediction coach. You analyze baseball matchups using statistical data, pitching matchups, park factors, and historical context.

Your analysis should be:
- Data-driven but accessible
- Concise (2-3 sentences for analysis)
- Clear on key factors affecting the outcome
- Honest about uncertainty

Respond ONLY with valid JSON in the exact format specified."""


def build_analysis_prompt(context: MatchupContext) -> str:
    """매치업 분석 프롬프트 생성."""
    fallback_note = ""
    if context.away_starter_fallback or context.home_starter_fallback:
        parts = []
        if context.away_starter_fallback:
            parts.append(f"{context.away_team_id} starter uses {context.away_starter_fallback} data")
        if context.home_starter_fallback:
            parts.append(f"{context.home_team_id} starter uses {context.home_starter_fallback} data")
        fallback_note = f"\nNote: {'; '.join(parts)} — actual starter stats may differ."

    # 엔진 예측이 있으면 포함
    engine_section = ""
    has_engine = context.engine_avg_total_runs > 0
    if has_engine:
        engine_section = f"""
## Engine Simulation (Monte Carlo)
Win probability: {context.away_team_id} {context.engine_away_win_pct:.1%} | {context.home_team_id} {context.engine_home_win_pct:.1%}
Projected score: {context.engine_avg_away_runs:.1f} - {context.engine_avg_home_runs:.1f}
Projected total: {context.engine_avg_total_runs:.1f} runs
"""

    return f"""Analyze this MLB matchup and provide your prediction.

## Matchup
{context.away_team_name} ({context.away_team_id}) @ {context.home_team_name} ({context.home_team_id})
Venue: {context.venue} | {context.game_time} ET

## Starting Pitchers
Away: {context.away_starter_name}
  K%: {context.away_starter_k_rate:.1%} | BB%: {context.away_starter_bb_rate:.1%} | HR/BIP: {context.away_starter_hr_rate:.1%}

Home: {context.home_starter_name}
  K%: {context.home_starter_k_rate:.1%} | BB%: {context.home_starter_bb_rate:.1%} | HR/BIP: {context.home_starter_hr_rate:.1%}
{engine_section}{fallback_note}

## Instructions
Provide your analysis as JSON with this exact structure:
{{
  "predicted_winner": "away" or "home",
  "confidence": 0.50 to 0.95,
  "predicted_away_score": integer,
  "predicted_home_score": integer,
  "key_factors": ["factor 1", "factor 2", "factor 3"],
  "analysis": "2-3 sentence analysis of the matchup",
  "risk_factors": ["risk 1", "risk 2"]
}}

Important:
- confidence should reflect genuine uncertainty (most games are 0.52-0.65)
- predicted_winner must be exactly "away" or "home"
- key_factors should be 3-5 specific, actionable factors
- Consider simulation data (if provided) and your baseball knowledge"""
