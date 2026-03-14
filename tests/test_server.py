"""2단계 검증: FastAPI 서버 엔드포인트 테스트."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from server.app import app

client: TestClient = None  # type: ignore


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_game():
    r = client.post("/game/new", json={
        "away_team_id": "NYY",
        "home_team_id": "BOS",
        "mode": "spectate",
        "away_philosophy": "analytics",
        "home_philosophy": "old_school",
        "seed": 42,
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert "game_id" in data
    assert data["state"]["inning"] == 1
    assert data["state"]["half"] == "top"
    assert data["state"]["is_game_over"] is False
    return data["game_id"]


def test_get_state():
    game_id = test_create_game()
    r = client.get(f"/game/{game_id}/state")
    assert r.status_code == 200
    assert r.json()["game_id"] == game_id


def test_advance_to_completion():
    """경기 끝까지 자동 진행."""
    r = client.post("/game/new", json={
        "away_team_id": "LAD",
        "home_team_id": "ATL",
        "mode": "spectate",
        "seed": 123,
    })
    game_id = r.json()["game_id"]

    max_plays = 500
    play_count = 0
    data = {}
    for _ in range(max_plays):
        r = client.post(f"/game/{game_id}/advance")
        assert r.status_code == 200
        data = r.json()
        play_count += 1

        if data.get("decision_required"):
            r2 = client.post(f"/game/{game_id}/decide", json={
                "action": "no_action", "reason": "auto",
            })
            assert r2.status_code == 200

        if data.get("is_game_over"):
            break

    assert data.get("is_game_over"), f"Game didn't end in {max_plays} plays"
    print(f"  Game completed in {play_count} plays")

    r = client.get(f"/game/{game_id}/boxscore")
    assert r.status_code == 200
    box = r.json()
    assert box["is_game_over"] is True
    assert box["winner"] in ("away", "home")
    print(f"  Score: {box['score']}, Winner: {box['winner']}")
    print(f"  Innings: {box['innings_played']}, Hits: {box['hits']}")

    r = client.get(f"/game/{game_id}/log")
    assert r.status_code == 200
    log = r.json()
    assert len(log) > 0
    print(f"  Play log entries: {len(log)}")


def test_advise_mode():
    """Advise 모드에서 결정 포인트 발생 확인."""
    r = client.post("/game/new", json={
        "away_team_id": "HOU",
        "home_team_id": "PHI",
        "mode": "advise",
        "seed": 99,
    })
    game_id = r.json()["game_id"]

    decision_points = 0
    max_plays = 500
    data = {}
    for _ in range(max_plays):
        r = client.post(f"/game/{game_id}/advance")
        data = r.json()

        if data.get("decision_required"):
            decision_points += 1
            ai_rec = data.get("ai_recommendation", {})
            action = ai_rec.get("action", "no_action")
            r2 = client.post(f"/game/{game_id}/decide", json={
                "action": action, "reason": "follow AI",
            })
            assert r2.status_code == 200

        if data.get("is_game_over"):
            break

    print(f"  Advise mode: {decision_points} decision points encountered")
    assert decision_points > 0, "Advise mode should have at least 1 decision point"


def test_404():
    r = client.get("/game/nonexistent/state")
    assert r.status_code == 404


def test_bad_team():
    r = client.post("/game/new", json={
        "away_team_id": "INVALID",
        "home_team_id": "BOS",
    })
    assert r.status_code == 400


if __name__ == "__main__":
    print("=" * 60)
    print(" Phase 1-C Stage 2 Validation: API Server Tests")
    print("=" * 60)
    print()

    tests = [
        ("Health", test_health),
        ("Create Game", test_create_game),
        ("Get State", test_get_state),
        ("Advance to Completion", test_advance_to_completion),
        ("Advise Mode", test_advise_mode),
        ("404 Handling", test_404),
        ("Bad Team", test_bad_team),
    ]

    with TestClient(app) as c:
        client = c
        passed = 0
        for name, fn in tests:
            try:
                print(f"── {name} ──")
                fn()
                print(f"  PASS")
                passed += 1
            except Exception as e:
                print(f"  FAIL: {e}")
            print()

        print(f"Results: {passed}/{len(tests)} passed")
