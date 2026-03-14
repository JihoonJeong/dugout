"""LLM Advisor 시스템 테스트 (API 키 없이 구조 검증)."""

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from advisor.base import MatchupContext, LLMAnalysis
from advisor.prompts import build_analysis_prompt, SYSTEM_PROMPT
from advisor.parser import parse_llm_response, _extract_json


def test_prompt_generation():
    """프롬프트 생성 테스트."""
    print("── Prompt Generation ──")

    ctx = MatchupContext(
        away_team_id="NYY", home_team_id="SFG",
        away_team_name="New York Yankees", home_team_name="San Francisco Giants",
        away_starter_name="Max Fried", home_starter_name="Logan Webb",
        venue="Oracle Park", game_time="20:05",
        engine_away_win_pct=0.55, engine_home_win_pct=0.45,
        engine_avg_away_runs=4.2, engine_avg_home_runs=3.5,
        engine_avg_total_runs=7.7,
        away_starter_k_rate=0.24, away_starter_bb_rate=0.07, away_starter_hr_rate=0.03,
        home_starter_k_rate=0.22, home_starter_bb_rate=0.06, home_starter_hr_rate=0.025,
    )

    prompt = build_analysis_prompt(ctx)
    assert "NYY" in prompt
    assert "SFG" in prompt
    assert "Max Fried" in prompt
    assert "Oracle Park" in prompt
    assert "55.0%" in prompt
    assert "predicted_winner" in prompt
    print(f"  System prompt: {len(SYSTEM_PROMPT)} chars ✓")
    print(f"  Analysis prompt: {len(prompt)} chars ✓")
    print(f"  Contains team IDs, starters, venue, engine data ✓")

    # With fallback
    ctx.away_starter_fallback = "team_avg"
    prompt2 = build_analysis_prompt(ctx)
    assert "team_avg" in prompt2
    print(f"  Fallback note included ✓")
    print()


def test_parser():
    """응답 파싱 테스트."""
    print("── Response Parsing ──")

    # 1. Clean JSON
    raw = '{"predicted_winner": "away", "confidence": 0.62, "predicted_away_score": 5, "predicted_home_score": 3, "key_factors": ["Strong away pitching", "Home park disadvantage"], "analysis": "NYY has the edge here.", "risk_factors": ["Bullpen fatigue"]}'
    result = parse_llm_response(raw, "anthropic", "claude-sonnet-4-20250514", 500)
    assert result.predicted_winner == "away"
    assert result.confidence == 0.62
    assert result.predicted_away_score == 5
    assert len(result.key_factors) == 2
    assert result.error is None
    print(f"  Clean JSON: ✓ (winner={result.predicted_winner}, conf={result.confidence})")

    # 2. JSON in code block
    raw2 = """Here's my analysis:

```json
{
  "predicted_winner": "home",
  "confidence": 0.58,
  "predicted_away_score": 3,
  "predicted_home_score": 4,
  "key_factors": ["Home field advantage", "Better bullpen"],
  "analysis": "Close game expected.",
  "risk_factors": ["Weather"]
}
```

Hope this helps!"""
    result2 = parse_llm_response(raw2, "openai", "gpt-4o", 600)
    assert result2.predicted_winner == "home"
    assert result2.confidence == 0.58
    print(f"  Code block JSON: ✓ (winner={result2.predicted_winner})")

    # 3. JSON with surrounding text
    raw3 = 'Based on my analysis, I think: {"predicted_winner": "away", "confidence": 0.55, "key_factors": ["Factor"], "analysis": "Test", "risk_factors": []} and that is my answer.'
    result3 = parse_llm_response(raw3, "google", "gemini-2.5-flash", 300)
    assert result3.predicted_winner == "away"
    print(f"  Embedded JSON: ✓ (winner={result3.predicted_winner})")

    # 4. Invalid JSON → error fallback
    raw4 = "I think the Yankees will win because they have great pitching."
    result4 = parse_llm_response(raw4, "anthropic", "claude-sonnet-4-20250514", 100)
    assert result4.error is not None
    assert result4.predicted_winner == "home"  # default
    print(f"  Invalid JSON fallback: ✓ (error={result4.error[:40]}...)")

    # 5. Confidence clamping
    raw5 = '{"predicted_winner": "away", "confidence": 1.5, "key_factors": [], "analysis": "", "risk_factors": []}'
    result5 = parse_llm_response(raw5, "openai", "gpt-4o", 100)
    assert result5.confidence == 1.0
    print(f"  Confidence clamping: ✓ (1.5 → {result5.confidence})")

    print()


def test_api_endpoints():
    """API 엔드포인트 구조 테스트."""
    print("── API Endpoint Tests ──")

    from fastapi.testclient import TestClient
    from server.app import app

    with TestClient(app) as client:
        # Providers
        r = client.get("/advisor/providers")
        assert r.status_code == 200
        providers = r.json()["providers"]
        assert len(providers) == 3
        names = [p["name"] for p in providers]
        assert "anthropic" in names
        assert "openai" in names
        assert "google" in names
        print(f"  GET /advisor/providers: {len(providers)} providers ✓")

        for p in providers:
            print(f"    {p['name']}: default={p['default_model']}, models={p['models']}")

        # Analyze with bad key → should fail gracefully
        r = client.post("/advisor/analyze", json={
            "provider": "anthropic",
            "api_key": "sk-ant-test-invalid-key-12345678",
            "away_team_id": "NYY",
            "home_team_id": "SFG",
            "engine_away_win_pct": 0.55,
            "engine_home_win_pct": 0.45,
        })
        assert r.status_code == 200  # returns result with error, not HTTP error
        data = r.json()
        assert data.get("error") is not None
        print(f"  POST /advisor/analyze (bad key): error returned ✓")

        # Analyze with too-short key → 400
        r = client.post("/advisor/analyze", json={
            "provider": "anthropic",
            "api_key": "short",
            "away_team_id": "NYY",
            "home_team_id": "SFG",
        })
        assert r.status_code == 400
        print(f"  POST /advisor/analyze (short key): 400 ✓")

        # Unknown provider → 400
        r = client.post("/advisor/analyze", json={
            "provider": "unknown",
            "api_key": "sk-ant-test-invalid-key-12345678",
            "away_team_id": "NYY",
            "home_team_id": "SFG",
        })
        assert r.status_code == 400
        print(f"  POST /advisor/analyze (unknown provider): 400 ✓")

    print()


if __name__ == "__main__":
    test_prompt_generation()
    test_parser()
    test_api_endpoints()
    print("All advisor tests passed!")
