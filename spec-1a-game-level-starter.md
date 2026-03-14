# Dugout — Phase 1-A: 경기별 선발투수 스펙

> **Version:** 0.1.0
> **Status:** Draft
> **Author:** JJ + Luca
> **Date:** 2026-03-13
> **의존성:** Phase 0 전체 (0-A, 0-B, 0-CD, 0-E)

---

## 1. 목적

2024 시즌 각 경기의 **실제 선발투수**를 반영하여 경기별 시뮬레이션을 수행.
Phase 0의 "팀당 대표 선발 1명 고정" 한계를 해소하고, 경기 예측의 정밀도를 높인다.

### 기대 효과

| 메트릭 | Phase 0 (고정) | Phase 1-A 목표 | 근거 |
|--------|---------------|---------------|------|
| L3 AUC | 0.634 | > 0.65 | 선발투수가 경기 승패에 가장 큰 단일 변수 |
| L3 Brier | 0.238 | < 0.235 | 매치업별 승률 분산이 생기면서 개선 |
| L4 RMSE | 11.32 | < 10.0 | 팀별 선발 로테이션 품질 차이 반영 |

---

## 2. 데이터: 경기별 선발투수 추출

### 2.1 데이터 소스

MLB Stats API (`statsapi` 패키지)를 사용하여 2024 전 경기의 선발투수를 추출.

```python
import statsapi

def fetch_season_schedule(season: int) -> list[GameRecord]:
    """
    시즌 전체 일정 + 선발투수 + 결과를 추출.
    
    Returns:
        list of GameRecord — 약 2,430경기 (30팀 × 162경기 / 2)
    """
    games = []
    
    # MLB Stats API: schedule endpoint
    # 날짜 범위로 조회 (2024-03-20 ~ 2024-09-29)
    schedule = statsapi.schedule(
        start_date="2024-03-20",
        end_date="2024-09-29"
    )
    
    for game in schedule:
        games.append(GameRecord(
            game_id=game["game_id"],
            date=game["game_date"],
            away_team=game["away_name"],       # 팀명 → team_id 매핑 필요
            home_team=game["home_name"],
            away_starter_id=game["away_probable_pitcher"],   # 이름 또는 ID
            home_starter_id=game["home_probable_pitcher"],
            away_score=game.get("away_score"),
            home_score=game.get("home_score"),
            status=game["status"],             # "Final", "Postponed" 등
        ))
    
    return games
```

### 2.2 GameRecord 데이터 구조

```python
@dataclass
class GameRecord:
    game_id: int
    date: str                          # "2024-04-15"
    away_team_id: str                  # "NYY"
    home_team_id: str                  # "BOS"
    away_starter_id: str               # player_id (FanGraphs 또는 MLB ID)
    home_starter_id: str               # player_id
    away_score: Optional[int]          # 실제 결과 (검증용)
    home_score: Optional[int]
    status: str                        # "Final", "Postponed", "Suspended"
    
    # 시뮬레이션 결과 (나중에 채워짐)
    sim_away_win_pct: Optional[float] = None
    sim_avg_away_runs: Optional[float] = None
    sim_avg_home_runs: Optional[float] = None
```

### 2.3 ID 매핑

MLB Stats API는 MLB ID를 반환하고, 엔진은 FanGraphs ID를 사용.
Phase 0-A의 id_mapping.py를 활용하여 변환.

```python
def resolve_starter(
    starter_info: str,               # MLB API에서 온 이름 또는 ID
    id_map: dict,                     # MLB ID → FanGraphs ID
    all_pitchers: dict[str, PitcherStats]
) -> Optional[PitcherStats]:
    """
    MLB API의 선발투수 정보를 엔진의 PitcherStats로 변환.
    
    매핑 실패 시:
      1. 이름으로 fuzzy match 시도
      2. 실패하면 None 반환 → fallback 로직에서 처리
    """
    pass
```

### 2.4 데이터 필터링

```
제외 대상:
  - status != "Final" (취소, 연기 경기)
  - 더블헤더 중 7이닝 경기 (2024 기준 해당 없을 수 있으나 방어적 체크)
  - 선발투수 정보 누락 경기 (opener 전략 등)
  
예상 유효 경기 수: ~2,400경기 (30경기 내외 제외)
```

---

## 3. 시뮬레이션 흐름 변경

### 3.1 Phase 0 방식 (기존)

```
각 팀 쌍에 대해:
  away = teams["NYY"]  (고정 선발: 팀 대표 1명)
  home = teams["BOS"]  (고정 선발: 팀 대표 1명)
  → 1,000회 시뮬레이션 → 승률
  → 같은 팀 매치업이면 항상 같은 승률
```

### 3.2 Phase 1-A 방식 (신규)

```
각 실제 경기에 대해:
  game_record = schedule[i]
  
  away_team = build_game_team(
      team_id=game_record.away_team_id,
      starter=resolve_starter(game_record.away_starter_id),
      data=dugout_data
  )
  home_team = build_game_team(
      team_id=game_record.home_team_id,
      starter=resolve_starter(game_record.home_starter_id),
      data=dugout_data
  )
  park = dugout_data.parks[home_team_park]
  
  → 1,000회 시뮬레이션 → 이 경기의 승률
  → 같은 NYY vs BOS라도 선발에 따라 다른 승률
```

### 3.3 경기별 팀 구성

```python
def build_game_team(
    team_id: str,
    starter: PitcherStats,
    data: DugoutData,
    lineup_mode: str = "fixed"    # "fixed" | "platoon" (Level 2)
) -> Team:
    """
    특정 경기를 위한 팀 구성.
    
    - 선발투수: 해당 경기의 실제 선발
    - 라인업: 팀 고정 라인업 (Level 1)
    - 불펜: 선발투수를 제외한 팀 RP진
    
    Args:
        team_id: 팀 약칭
        starter: 해당 경기 선발투수의 PitcherStats
        data: DugoutData (Phase 0-A 산출물)
        lineup_mode: 라인업 결정 방식
    """
    
    base_team = data.teams[team_id]
    
    # 불펜: 기존 불펜에서 선발투수 제외 (만약 겸용이면)
    bullpen = [p for p in base_team.bullpen if p.player_id != starter.player_id]
    
    # 라인업: Level 1에서는 기존 고정 라인업
    lineup = base_team.lineup
    
    return Team(
        team_id=team_id,
        name=base_team.name,
        lineup=lineup,
        starter=starter,
        bullpen=bullpen
    )
```

---

## 4. Fallback 처리

### 4.1 선발투수를 엔진 데이터에서 찾을 수 없는 경우

```
원인:
  - 시즌 중 콜업된 신인 (PA/IP가 적어 0-A에서 누락)
  - ID 매핑 실패
  - Opener 전략 (불펜 투수가 선발로 등록)

Fallback 전략 (순서):
  1. 해당 선수의 데이터가 있지만 ID 매핑만 실패 → 이름 fuzzy match
  2. 데이터가 없는 신인 → 해당 팀 투수진 평균 스탯으로 대체
  3. 완전 매핑 실패 → 리그 평균 투수로 대체 + 경고 로그

각 fallback 사용 횟수를 기록하여 리포트에 포함.
목표: fallback 사용률 < 5% (약 120경기 미만)
```

### 4.2 팀 데이터 자체가 없는 경우

```
2024 시즌 중 팀명/약칭이 변경된 경우는 없으므로 발생 가능성 낮음.
TEAM_MAPPING과 MLB API 팀명 사이의 매핑 테이블 필요.
```

---

## 5. 팀명 매핑

MLB Stats API가 반환하는 팀명과 엔진 내부 team_id 간 매핑.

```python
MLB_API_TO_TEAM_ID = {
    "Arizona Diamondbacks": "ARI",
    "Atlanta Braves": "ATL",
    "Baltimore Orioles": "BAL",
    "Boston Red Sox": "BOS",
    "Chicago Cubs": "CHC",
    "Chicago White Sox": "CHW",
    "Cincinnati Reds": "CIN",
    "Cleveland Guardians": "CLE",
    "Colorado Rockies": "COL",
    "Detroit Tigers": "DET",
    "Houston Astros": "HOU",
    "Kansas City Royals": "KCR",
    "Los Angeles Angels": "LAA",
    "Los Angeles Dodgers": "LAD",
    "Miami Marlins": "MIA",
    "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN",
    "New York Mets": "NYM",
    "New York Yankees": "NYY",
    "Oakland Athletics": "OAK",
    "Philadelphia Phillies": "PHI",
    "Pittsburgh Pirates": "PIT",
    "San Diego Padres": "SDP",
    "San Francisco Giants": "SFG",
    "Seattle Mariners": "SEA",
    "St. Louis Cardinals": "STL",
    "Tampa Bay Rays": "TBR",
    "Texas Rangers": "TEX",
    "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WSN",
}
```

---

## 6. 실행 파이프라인

### 6.1 전체 흐름

```python
def run_game_level_simulation(
    data: DugoutData,
    season: int = 2024,
    n_sims: int = 1000,
    seed: int = 42
) -> GameLevelResults:
    """
    2024 전 경기에 대해 경기별 선발투수를 반영한 시뮬레이션 실행.
    
    Steps:
      1. 경기 일정 + 선발투수 추출 (또는 캐시 로드)
      2. 각 경기에 대해 팀 구성 → 시뮬레이션 → 승률 산출
      3. 실제 결과와 비교하여 검증 메트릭 산출
    """
    
    rng = np.random.default_rng(seed)
    
    # 1. 일정 데이터
    schedule = load_or_fetch_schedule(season)
    
    # 2. 경기별 시뮬레이션
    results = []
    fallback_count = {"fuzzy": 0, "team_avg": 0, "league_avg": 0}
    
    for game in schedule:
        if game.status != "Final":
            continue
        
        # 선발투수 해결
        away_starter, fb_a = resolve_starter_with_fallback(
            game.away_starter_id, game.away_team_id, data
        )
        home_starter, fb_h = resolve_starter_with_fallback(
            game.home_starter_id, game.home_team_id, data
        )
        fallback_count[fb_a] += 1 if fb_a else 0
        fallback_count[fb_h] += 1 if fb_h else 0
        
        # 팀 구성
        away_team = build_game_team(game.away_team_id, away_starter, data)
        home_team = build_game_team(game.home_team_id, home_starter, data)
        park = data.parks[TEAM_MAPPING[game.home_team_id]["park"]]
        
        # 시뮬레이션
        series = simulate_series(away_team, home_team, park, data.league,
                                  n_simulations=n_sims, seed=rng.integers(1e9))
        
        # 결과 기록
        game.sim_away_win_pct = series.away_win_pct
        game.sim_avg_away_runs = series.avg_away_runs
        game.sim_avg_home_runs = series.avg_home_runs
        results.append(game)
    
    return GameLevelResults(
        games=results,
        fallback_stats=fallback_count,
        n_sims_per_game=n_sims
    )
```

### 6.2 성능 고려

```
경기 수: ~2,400
시뮬레이션/경기: 1,000
총 시뮬레이션: ~2,400,000 경기

Phase 0 벤치마크에서 1,000경기 시뮬레이션 소요 시간을 기준으로 추정.
만약 1,000경기에 10초 → 전체 약 24초.
만약 1,000경기에 60초 → 전체 약 144초 (2.4분).

허용 범위. 병렬화는 V0.1에서 불필요.

빠른 검증용: n_sims=100으로 줄여서 10분의 1 시간.
```

---

## 7. 검증: Phase 0 대비 개선 측정

### 7.1 L3 재검증 (경기별 예측)

```
Phase 0 방식:
  같은 팀 매치업 → 같은 승률 → AUC 0.634

Phase 1-A 방식:
  같은 NYY vs BOS라도 선발에 따라 다른 승률 → AUC 개선 기대

비교 항목:
  - AUC: 0.634 → 목표 > 0.65
  - Brier: 0.238 → 목표 < 0.235
  - Log Loss: 0.670 → 목표 < 0.665
  - 칼리브레이션: 승률 분포가 더 넓어져야 함 (0.3~0.7 → 0.25~0.75)
```

### 7.2 L4 재검증 (시즌 승수)

```
Phase 0 방식:
  팀별 고정 대표 선발로 전 경기 동일 시뮬레이션

Phase 1-A 방식:
  경기별 실제 선발로 시뮬레이션 → 승패 합산 → 시즌 승수

기대 효과:
  - 로테이션 품질이 높은 팀 (LAD, PHI 등)의 예측 정확도 향상
  - 에이스 의존도가 높은 팀의 승수를 더 정확히 반영
  - RMSE: 11.32 → 목표 < 10.0
```

### 7.3 선발투수 임팩트 분석 (신규)

```
새로 추가할 분석:
  1. 선발투수별 승률 분포
     - 같은 팀이라도 에이스 vs 5선발의 승률 차이 측정
     - 예: Cole 선발 시 NYY 승률 58% vs Schmidt 선발 시 48%
  
  2. 선발투수 교체의 게임당 평균 승률 변동
     - 팀 고정 승률 대비 선발에 따른 변동폭 (standard deviation)
     - 이 값이 클수록 선발투수 반영의 가치가 높음
  
  3. Fallback 사용 빈도 및 영향
     - fallback 경기 제외 시 메트릭 변화
     - fallback이 메트릭을 악화시키면 매핑 개선 필요
```

### 7.4 A/B 비교 자동화

```python
# metrics_history.json에 v0.1.1 (Phase 0 최종)과 v1.0-A (Phase 1-A) 기록
# compare.py로 자동 비교 리포트 생성

{
    "v0.1.1": {
        "date": "2026-03-13",
        "changes": "Phase 0 final — IBB fix, splits, L1 redesign",
        "l3_auc": 0.634,
        "l3_brier": 0.238,
        "l4_wins_rmse": 11.32
    },
    "v1.0-A": {
        "date": "...",
        "changes": "Game-level starting pitcher",
        "l3_auc": "...",
        "l3_brier": "...",
        "l4_wins_rmse": "..."
    }
}
```

---

## 8. Level 2 확장 준비: Platoon 라인업 (미구현, 설계만)

Phase 1-A의 Level 1 결과를 보고, Level 2 확장 여부를 판단.

### 설계 초안

```python
def build_game_team_platoon(
    team_id: str,
    starter: PitcherStats,
    opponent_starter: PitcherStats,  # 상대 선발 (platoon 판단용)
    data: DugoutData
) -> Team:
    """
    Level 2: 상대 선발투수의 좌/우에 따라 라인업 자동 조정.
    
    로직:
      1. 상대 선발이 좌완 → 팀 라인업에서 좌타 비중 줄이고 우타 추가
      2. 상대 선발이 우완 → 기본 라인업 유지 (대부분의 타자가 우타자 상대 성적이 기본)
      3. 스위치 히터는 항상 포함
    
    구현:
      팀의 전체 타자 풀 (PA ≥ 50)에서:
        - 상대 투수 hand에 대한 wOBA가 높은 순으로 9명 선발
        - 포지션 제약은 V1에서 무시 (모든 타자가 DH 가능 가정)
    """
    pass  # Level 2에서 구현
```

### Level 2 진입 조건

```
Level 1 결과에서:
  - L3 AUC 개선폭이 < 0.01이면: 선발투수 반영만으로 부족 → Level 2 진행
  - L3 AUC 개선폭이 > 0.02이면: 선발투수 반영만으로 충분 → Level 2 미룸
  - 중간이면: 선발투수 임팩트 분석의 변동폭을 보고 판단
```

---

## 9. V1-A 명시적 제외 사항

| 제외 항목 | 이유 | 예정 Phase |
|----------|------|-----------|
| 실제 일일 라인업 반영 | 데이터 추출/매핑 복잡 | 1-A Level 2 또는 1-B |
| 불펜 피로 (전날 등판 여부) | 일별 상태 추적 필요 | 1-C (AI 감독) |
| 선발투수 구수/피로 (등판 간격) | 등판 간격별 성적 모델 필요 | 1-B |
| 포스트시즌 경기 | 정규시즌만 검증 | 2+ |
| 시즌 중 트레이드 반영 | 1-B (시간대별 스탯) 영역 | 1-B |
| 부상 IL 반영 | 1-B 영역 | 1-B |

---

## 10. 구현 노트 (Claude Code용)

### 디렉토리 구조

```
dugout/
├── engine/                        # Phase 0 (변경 없음)
├── data/
│   ├── ...                        # Phase 0-A (기존)
│   ├── schedule.py                # 경기 일정 + 선발투수 추출 (신규)
│   ├── game_team_builder.py       # 경기별 팀 구성 (신규)
│   └── team_name_mapping.py       # MLB API ↔ team_id 매핑 (신규)
├── simulation/
│   ├── __init__.py
│   ├── game_level.py              # 경기별 시뮬레이션 실행 (이 스펙의 핵심)
│   └── results.py                 # GameLevelResults 데이터 클래스
├── validation/
│   ├── ...                        # Phase 0-E (기존)
│   ├── l3_game_v2.py              # L3 경기별 예측 (선발투수 반영 버전)
│   └── starter_impact.py          # 선발투수 임팩트 분석 (신규)
├── cache/
│   ├── ...                        # Phase 0 (기존)
│   └── schedule_2024.json         # 경기 일정 캐시 (신규)
├── tests/
│   ├── ...                        # Phase 0 (기존)
│   ├── test_schedule.py           # 일정 추출 테스트
│   ├── test_game_team_builder.py  # 경기별 팀 구성 테스트
│   └── test_game_level_sim.py     # 경기별 시뮬레이션 통합 테스트
└── metrics_history.json
```

### 핵심 원칙

1. **Phase 0 엔진을 수정하지 않는다.** 1-A는 엔진 위에 "경기별 선발투수 교체"라는 래퍼를 올리는 것. `simulate_game`, `simulate_series` 함수는 그대로 사용.

2. **일정 데이터는 반드시 캐싱.** MLB Stats API 호출을 매번 하면 느리고 rate limit에 걸림. `schedule_2024.json`으로 한 번 저장하고 재사용.

3. **Fallback을 투명하게 기록.** 어떤 경기에서 어떤 fallback이 사용되었는지 전부 로그. 리포트에서 fallback 사용률과 메트릭 영향을 분석할 수 있어야 함.

4. **Phase 0 검증과 1-A 검증을 동시에 돌릴 수 있어야 함.** A/B 비교가 핵심이므로, 같은 검증 프레임워크에서 "고정 선발" vs "경기별 선발" 모드를 스위치로 전환 가능하게.

5. **시뮬레이션 횟수 조절 가능.** 전체 2,400경기 × 1,000회는 시간이 걸리므로, 빠른 검증용 `n_sims=100` 모드와 정밀 검증용 `n_sims=1000` 모드를 지원.

---

## 부록 A: 선발투수 교체의 예상 임팩트

### 직관적 추정

```
2024 MLB 평균:
  - 팀 에이스의 ERA: ~3.00
  - 팀 5선발의 ERA: ~5.00
  - ERA 차이 2.00 → 경기당 약 2점 차이 (9이닝 기준)
  
  이 득점 차이가 승률에 미치는 영향:
  - 리그 평균 4.3 R/G 기준
  - 에이스 상대: 3.3 R/G 허용 → 승률 ~58%
  - 5선발 상대: 5.3 R/G 허용 → 승률 ~42%
  - 차이: ~16%p
  
  Phase 0에서는 이 16%p 차이가 반영되지 않고 팀 평균으로 뭉뚱그려짐.
  Phase 1-A에서 이 분산이 살아나면 예측 정밀도가 개선됨.
```

### AUC 개선 추정

```
AUC 0.634 → ?

선발투수 반영은 "예측 확률의 분산을 넓히는" 효과.
현재 같은 팀 매치업이 항상 52%라면, 1-A 후에는 45~60% 범위로 퍼짐.
이 추가 분산이 실제 결과와 상관을 가지면 AUC가 올라감.

보수적 추정: +0.02 (→ 0.654)
낙관적 추정: +0.04 (→ 0.674)
목표: > 0.65
```

---

## 부록 B: 예시 — 같은 매치업, 다른 선발

```
2024-04-15: NYY @ BOS
  선발: Gerrit Cole (NYY) vs Brayan Bello (BOS)
  Cole: K%=29.8%, BB%=5.8%, FIP=3.10
  Bello: K%=21.5%, BB%=7.2%, FIP=4.20
  → 시뮬레이션 승률: NYY 58.2%

2024-07-22: NYY @ BOS
  선발: Marcus Stroman (NYY) vs Kutter Crawford (BOS)
  Stroman: K%=16.8%, BB%=8.0%, FIP=4.80
  Crawford: K%=24.1%, BB%=6.5%, FIP=3.60
  → 시뮬레이션 승률: NYY 44.1%

차이: 14.1%p — 같은 팀이지만 선발에 따라 완전히 다른 경기.
Phase 0에서는 이 두 경기가 동일한 승률(~52%)로 예측되었음.
```
