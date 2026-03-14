# Dugout — Phase 0-CD: 게임 시뮬레이션 스펙

> **Version:** 0.1.0
> **Status:** Draft
> **Author:** JJ + Luca
> **Date:** 2026-03-12
> **의존성:** Phase 0-B (타석 확률 모델)

---

## 1. 목적

타석 확률 모델(0-B)을 기반으로, 한 경기(9이닝+)를 처음부터 끝까지 시뮬레이션하는 엔진.
타석 결과 → 주자 진루 → 득점 → 이닝 전환 → 경기 종료까지의 전체 흐름을 구현한다.

이 모듈이 완성되면:
- 두 팀의 경기를 N회 Monte Carlo 시뮬레이션하여 승률 추정 가능
- 팀별 평균 득점, 득점 분포 산출 가능
- Phase 0-E 검증 프레임워크의 입력이 됨

---

## 2. 게임 상태 (GameState)

경기의 모든 순간을 표현하는 상태 객체.

### 데이터 구조

```python
@dataclass
class GameState:
    # 이닝 정보
    inning: int                    # 1~N (현재 이닝)
    half: str                      # "top" | "bottom"
    outs: int                      # 0, 1, 2
    
    # 주자 상태
    runners: dict[str, Runner]     # {"1B": Runner, "2B": Runner, "3B": Runner}
                                   # 비어있으면 해당 베이스 주자 없음
    
    # 점수
    score: dict[str, int]          # {"away": 0, "home": 0}
    
    # 타순
    batting_order_idx: dict[str, int]  # {"away": 0, "home": 0}
                                       # 현재 타순 인덱스 (0~8)
    
    # 투수 상태
    current_pitcher: dict[str, PitcherState]  # {"away": PitcherState, "home": PitcherState}
    
    # 경기 상태
    game_over: bool
    
    # 기록 (선택적, 분석용)
    play_log: list[PlayEvent]      # 모든 플레이 기록


@dataclass
class Runner:
    player_id: str
    name: str
    from_base: str                 # 이 타석 시작 시 있던 베이스 ("1B", "2B", "3B")


@dataclass
class PitcherState:
    pitcher: PitcherStats          # 0-B의 PitcherStats
    pitch_count: int               # 현재 구수
    innings_pitched: float         # 투구 이닝 (예: 5.2 = 5이닝 2아웃)
    is_starter: bool
    
    
@dataclass
class PlayEvent:
    inning: int
    half: str
    batter: str                    # player_id
    pitcher: str                   # player_id
    event: str                     # "K", "1B", "HR", "GO_DP", "FO_SF" 등
    runners_before: dict           # 플레이 전 주자 상태
    runners_after: dict            # 플레이 후 주자 상태
    runs_scored: int               # 이 플레이로 득점한 수
    outs_before: int
    outs_after: int
    description: str               # 인간이 읽을 수 있는 설명
```

---

## 3. 주자 진루 모델

### 3.1 진루 확률 테이블

타석 결과 × 현재 주자 상태 → 주자 이동 확률 분포.
리그 평균 기반 확률 테이블을 사용한다 (V0.2+에서 선수별 sprint speed 보정 추가 예정).

아래 테이블의 확률은 **Retrosheet 2019-2023 play-by-play 데이터 기반 근사값**이며,
Phase 0-A에서 실제 데이터 추출 시 업데이트한다.

#### 싱글 (1B) 시 주자 진루

| 주자 상태 | 결과 | 확률 |
|-----------|------|------|
| 1루 주자 | → 2루 | 0.40 |
| 1루 주자 | → 3루 | 0.50 |
| 1루 주자 | → 홈 (득점) | 0.10 |
| 2루 주자 | → 3루 | 0.30 |
| 2루 주자 | → 홈 (득점) | 0.70 |
| 3루 주자 | → 홈 (득점) | 0.95 |
| 3루 주자 | → 3루 잔류 | 0.05 |
| 타자 | → 1루 | 1.00 |

*참고: 주자가 여러 명일 때, 각 주자는 독립적으로 진루 확률을 적용한다.*
*단, 앞 주자가 진루하지 않으면 뒷 주자가 해당 베이스를 넘어갈 수 없다 (물리적 제약).*

#### 더블 (2B) 시 주자 진루

| 주자 상태 | 결과 | 확률 |
|-----------|------|------|
| 1루 주자 | → 3루 | 0.45 |
| 1루 주자 | → 홈 (득점) | 0.55 |
| 2루 주자 | → 홈 (득점) | 0.95 |
| 2루 주자 | → 3루 | 0.05 |
| 3루 주자 | → 홈 (득점) | 1.00 |
| 타자 | → 2루 | 1.00 |

#### 트리플 (3B) 시 주자 진루

| 주자 상태 | 결과 | 확률 |
|-----------|------|------|
| 모든 주자 | → 홈 (득점) | 1.00 |
| 타자 | → 3루 | 1.00 |

#### 홈런 (HR) 시 주자 진루

| 주자 상태 | 결과 | 확률 |
|-----------|------|------|
| 모든 주자 | → 홈 (득점) | 1.00 |
| 타자 | → 홈 (득점) | 1.00 |

#### 볼넷 (BB) / 사구 (HBP) 시 주자 진루

포스 진루만 발생:

| 주자 상태 | 결과 |
|-----------|------|
| 타자 | → 1루 |
| 1루 주자 (있을 때) | → 2루 (포스) |
| 2루 주자 (1루에도 주자 있을 때) | → 3루 (포스) |
| 3루 주자 (1,2루 모두 주자 있을 때) | → 홈 (득점, 밀어내기) |

*포스가 아닌 주자는 이동하지 않음. 예: 주자 1,3루에서 BB → 타자 1루, 1루 주자 → 2루, 3루 주자는 그대로 3루.*

#### 삼진 (K) 시

모든 주자 그대로. 1아웃 추가.

### 3.2 주자 진루 해결 알고리즘

복수 주자가 있을 때의 충돌을 해결하는 알고리즘:

```
function resolve_runners(event, runners_before, rng):
    """
    타석 결과에 따라 모든 주자의 새 위치를 결정.
    
    핵심 원칙:
    1. 뒤에서부터 처리 (3루 → 2루 → 1루 → 타자)
    2. 앞 주자가 점유 중인 베이스에는 진입 불가
    3. 포스 상황에서는 강제 진루
    """
    
    runners_after = {}
    runs_scored = 0
    
    if event in ("HR",):
        # 모든 주자 + 타자 홈
        runs_scored = len(runners_before) + 1
        return runners_after, runs_scored
    
    if event in ("3B",):
        # 모든 주자 홈, 타자 3루
        runs_scored = len(runners_before)
        runners_after["3B"] = Runner(batter)
        return runners_after, runs_scored
    
    if event in ("BB", "HBP"):
        return resolve_force_advance(runners_before, batter)
    
    if event in ("K",):
        return dict(runners_before), 0  # 주자 변동 없음
    
    if event in ("GO", "FO"):
        # 별도 처리 (섹션 4 참조)
        return resolve_out_runners(event, runners_before, outs, rng)
    
    if event in ("1B", "2B"):
        # 확률적 진루
        # 3루 주자부터 역순으로 처리
        occupied = set()
        
        for base in ["3B", "2B", "1B"]:
            if base in runners_before:
                # 해당 진루 테이블에서 확률 샘플링
                dest = sample_advance(event, base, rng)
                
                # 앞 베이스가 점유 중이면 한 단계 뒤로 조정
                while dest in occupied and dest != "HOME":
                    dest = prev_base(dest)
                
                if dest == "HOME":
                    runs_scored += 1
                else:
                    runners_after[dest] = runners_before[base]
                    occupied.add(dest)
        
        # 타자 배치
        batter_dest = "1B" if event == "1B" else "2B"
        if batter_dest in occupied:
            # 이론적으로 발생하지 않아야 하지만 방어적 처리
            batter_dest = next_base(batter_dest)
        runners_after[batter_dest] = Runner(batter)
        
        return runners_after, runs_scored
```

### 3.3 V0.2+ 확장 예정

| 항목 | 설명 |
|------|------|
| 선수별 sprint speed 보정 | Statcast sprint speed로 진루 확률 조정 |
| 타구 방향 반영 | 좌측/중앙/우측 안타에 따른 진루 차이 |
| 외야수 어깨 보정 | 외야수 arm strength에 따른 진루 억제 |
| 도루 | Phase 1에서 AI 감독 결정과 연동 |

---

## 4. 아웃 처리

### 4.1 땅볼 아웃 (GO)

#### 더블플레이 (DP)

```
조건: GO + 아웃 < 2 + 1루 주자 존재

DP 확률: 0.55 (리그 평균 — 적격 상황 대비 DP 전환 비율)

DP 발생 시:
  - 2아웃 추가 (타자 + 포스아웃된 주자)
  - 가장 앞의 포스 주자가 아웃 (일반적으로 2루에서)
  - 나머지 주자: 한 베이스 진루 (비포스 주자는 그대로)
  
  예시: 주자 1,3루 0아웃 GO → DP
    → 타자 아웃 + 1루 주자 2루 포스아웃 (2아웃 추가)
    → 3루 주자: 홈 득점 확률 0.50 / 잔류 0.50

DP 미발생 시 (일반 GO):
  - 1아웃 추가 (타자)
  - 주자 진루 (아래 테이블)
```

#### GO 시 주자 진루 (DP 아닌 경우)

| 주자 상태 | 결과 | 확률 |
|-----------|------|------|
| 1루 주자 | → 2루 | 0.70 |
| 1루 주자 | → 1루 잔류 | 0.30 |
| 2루 주자 | → 3루 | 0.55 |
| 2루 주자 | → 2루 잔류 | 0.45 |
| 3루 주자 (아웃 < 2) | → 홈 (득점) | 0.50 |
| 3루 주자 (아웃 < 2) | → 3루 잔류 | 0.50 |
| 3루 주자 (아웃 = 2) | → 3루 잔류 | 1.00 |

*참고: 3루 주자가 GO에 홈으로 들어오는 것은 2아웃이 아닐 때만 시도.*

### 4.2 뜬공 아웃 (FO)

#### 희생플라이 (Sacrifice Fly)

```
조건: FO + 아웃 < 2 + 3루 주자 존재

희생플라이 확률: 0.65 (3루 주자가 태그업 후 홈으로 득점하는 비율)

SF 발생 시:
  - 1아웃 추가 (타자)
  - 3루 주자 홈 득점
  - 다른 주자: 태그업 진루 가능 (아래 테이블)
  
SF 미발생 시 (일반 FO):
  - 1아웃 추가 (타자)
  - 주자 이동 없음 (태그업 실패)
```

#### FO 시 태그업 진루 (아웃 < 2)

| 주자 상태 | 결과 | 확률 |
|-----------|------|------|
| 1루 주자 | → 2루 (태그업) | 0.10 |
| 1루 주자 | → 1루 잔류 | 0.90 |
| 2루 주자 | → 3루 (태그업) | 0.35 |
| 2루 주자 | → 2루 잔류 | 0.65 |

*참고: 2아웃에서 FO는 이닝 종료이므로 태그업 진루 불필요.*

### 4.3 아웃 처리 의사코드

```
function resolve_out_runners(event, runners_before, outs, rng):
    runners_after = {}
    runs_scored = 0
    outs_added = 1  # 타자 아웃
    
    if event == "GO":
        # DP 판정
        has_force = "1B" in runners_before
        dp_eligible = (outs < 2) and has_force
        
        if dp_eligible and rng.random() < 0.55:
            # 더블플레이 발생
            outs_added = 2
            
            # 포스 주자 중 가장 앞(2루 방향) 아웃
            # 1루 주자 제거 (2루 포스아웃)
            remaining = {k: v for k, v in runners_before.items() if k != "1B"}
            
            # 나머지 주자 진루
            for base in ["3B", "2B"]:
                if base in remaining:
                    if base == "3B":
                        if rng.random() < 0.50:
                            runs_scored += 1  # 홈 득점
                        else:
                            runners_after["3B"] = remaining["3B"]
                    elif base == "2B":
                        runners_after["3B"] = remaining["2B"]
        else:
            # 일반 GO (DP 아님)
            for base in ["3B", "2B", "1B"]:
                if base in runners_before:
                    dest = sample_go_advance(base, outs, rng)
                    if dest == "HOME":
                        runs_scored += 1
                    else:
                        runners_after[dest] = runners_before[base]
    
    elif event == "FO":
        # 희생플라이 판정
        has_third = "3B" in runners_before
        sf_eligible = (outs < 2) and has_third
        
        if sf_eligible and rng.random() < 0.65:
            # 희생플라이 — 3루 주자 득점
            runs_scored += 1
            
            # 나머지 주자 태그업
            for base in ["2B", "1B"]:
                if base in runners_before:
                    dest = sample_fo_tagup(base, rng)
                    runners_after[dest] = runners_before[base]
        else:
            # 일반 FO — 주자 이동 없음 (태그업 시도는 별도)
            if outs < 2:
                for base in ["2B", "1B"]:
                    if base in runners_before:
                        dest = sample_fo_tagup(base, rng)
                        runners_after[dest] = runners_before[base]
                # 3루 주자는 태그업 실패 시 잔류
                if has_third:
                    runners_after["3B"] = runners_before["3B"]
            else:
                runners_after = dict(runners_before)
                if "3B" in runners_after:
                    runners_after["3B"] = runners_before["3B"]
    
    return runners_after, runs_scored, outs_added
```

---

## 5. 경기 흐름 (Game Loop)

### 5.1 전체 경기 구조

```
function simulate_game(away_team, home_team, park, league, rng) -> GameResult:
    
    state = GameState(
        inning=1, half="top", outs=0,
        runners={},
        score={"away": 0, "home": 0},
        batting_order_idx={"away": 0, "home": 0},
        current_pitcher={
            "away": PitcherState(away_team.starter, pitch_count=0, ip=0.0, is_starter=True),
            "home": PitcherState(home_team.starter, pitch_count=0, ip=0.0, is_starter=True)
        },
        game_over=False,
        play_log=[]
    )
    
    while not state.game_over:
        simulate_half_inning(state, away_team, home_team, park, league, rng)
        advance_half_inning(state)
    
    return GameResult(state)
```

### 5.2 하프이닝

```
function simulate_half_inning(state, away_team, home_team, park, league, rng):
    
    batting_side = "away" if state.half == "top" else "home"
    pitching_side = "home" if state.half == "top" else "away"
    
    batting_team = away_team if batting_side == "away" else home_team
    pitcher_state = state.current_pitcher[pitching_side]
    
    # 연장 10회+ Manfred Runner: 무사 2루 자동 배치
    if state.inning >= 10 and state.outs == 0 and len(state.runners) == 0:
        place_manfred_runner(state, batting_team)
    
    state.outs = 0
    state.runners = {} if state.inning < 10 else state.runners  # Manfred runner 유지
    
    while state.outs < 3:
        # 투수 교체 판정
        pitcher_state = check_pitching_change(state, pitching_side, 
                                                batting_team if pitching_side == "away" else home_team if pitching_side == "home" else None,
                                                away_team if pitching_side == "away" else home_team)
        
        # 현재 타자
        batter_idx = state.batting_order_idx[batting_side]
        batter = batting_team.lineup[batter_idx]
        pitcher = pitcher_state.pitcher
        
        # 타석 시뮬레이션 (Phase 0-B)
        ab_result = simulate_at_bat(batter, pitcher, league, park, rng)
        
        # 투구 수 업데이트 (타석당 평균 구수 근사)
        pitches_this_ab = estimate_pitch_count(ab_result.event, rng)
        pitcher_state.pitch_count += pitches_this_ab
        
        # 주자 진루 해결
        runners_after, runs, outs_added = resolve_play(
            ab_result.event, state.runners, state.outs, batter, rng
        )
        
        # 상태 업데이트
        state.runners = runners_after
        state.score[batting_side] += runs
        state.outs += outs_added
        
        # 투구 이닝 업데이트
        pitcher_state.innings_pitched += outs_added / 3.0
        
        # 플레이 기록
        state.play_log.append(PlayEvent(...))
        
        # 타순 진행
        state.batting_order_idx[batting_side] = (batter_idx + 1) % 9
        
        # 9회말 이후 홈팀 리드 시 워크오프 체크
        if is_walkoff(state):
            state.game_over = True
            return
```

### 5.3 이닝 전환

```
function advance_half_inning(state):
    
    if state.half == "top":
        state.half = "bottom"
        state.outs = 0
        state.runners = {}
        
        # 9회말: 홈팀이 이미 리드 중이면 경기 종료 (X)
        if state.inning >= 9 and state.score["home"] > state.score["away"]:
            state.game_over = True
            return
    
    else:  # bottom 끝
        # 9회 이상이고 동점이 아니면 경기 종료
        if state.inning >= 9 and state.score["home"] != state.score["away"]:
            state.game_over = True
            return
        
        # 동점이면 연장
        state.inning += 1
        state.half = "top"
        state.outs = 0
        state.runners = {}
```

### 5.4 워크오프 처리

```
function is_walkoff(state) -> bool:
    """9회말 이후, 홈팀이 역전 또는 동점→리드 시 즉시 종료"""
    if state.half != "bottom":
        return False
    if state.inning < 9:
        return False
    return state.score["home"] > state.score["away"]
```

---

## 6. 투수 교체 (V0.1 자동 규칙)

V0.1에서는 AI 감독 없이, 규칙 기반으로 투수를 교체한다.
Phase 1에서 AI 감독이 이 결정권을 가져간다.

### 6.1 교체 규칙

```
function check_pitching_change(state, pitching_side, pitching_team) -> PitcherState:
    
    ps = state.current_pitcher[pitching_side]
    
    # 선발 투수 교체 조건 (둘 중 하나 충족 시)
    if ps.is_starter:
        should_change = (
            ps.pitch_count >= 100 or      # 100구 도달
            ps.innings_pitched >= 6.0      # 6이닝 완료
        )
        
        if should_change:
            # 불펜에서 다음 투수
            next_reliever = pitching_team.get_next_reliever()
            new_ps = PitcherState(
                pitcher=next_reliever,
                pitch_count=0,
                innings_pitched=0.0,
                is_starter=False
            )
            state.current_pitcher[pitching_side] = new_ps
            return new_ps
    
    # 불펜 투수 교체 조건: 1이닝 완료 시
    else:
        if ps.innings_pitched >= 1.0:
            next_reliever = pitching_team.get_next_reliever()
            if next_reliever is not None:  # 불펜 소진 시 현재 투수 계속
                new_ps = PitcherState(
                    pitcher=next_reliever,
                    pitch_count=0,
                    innings_pitched=0.0,
                    is_starter=False
                )
                state.current_pitcher[pitching_side] = new_ps
                return new_ps
    
    return ps  # 교체 없음


# 교체 타이밍: 이닝 시작 시 또는 타석 사이에 발생
# 타석 중간에는 교체하지 않음
```

### 6.2 타석당 투구 수 추정

실제 투구 수를 정밀하게 시뮬레이션하지 않고, 타석 결과별 평균 구수로 근사한다.

```
function estimate_pitch_count(event, rng) -> int:
    """타석 결과에 따른 투구 수 근사 (리그 평균 기반)"""
    
    mean_pitches = {
        "K":   4.9,   # 삼진은 구수가 많음
        "BB":  5.6,   # 볼넷은 가장 많음
        "HBP": 2.5,   # 사구는 적음
        "1B":  3.8,
        "2B":  3.7,
        "3B":  3.5,
        "HR":  3.4,   # 홈런은 비교적 빨리 결정
        "GO":  3.4,
        "FO":  3.6,
    }
    
    # 평균 주변에서 ±1.5 범위 내 정수로 샘플링
    mean = mean_pitches[event]
    count = max(1, round(rng.normal(mean, 1.0)))
    return min(count, 12)  # 최대 12구 (현실적 상한)
```

---

## 7. 팀 구성 (Team)

### 데이터 구조

```python
@dataclass
class Team:
    team_id: str
    name: str
    lineup: list[BatterStats]      # 9명 타순 (index 0 = 1번 타자)
    starter: PitcherStats          # 선발 투수
    bullpen: list[PitcherStats]    # 불펜 투수 (사용 순서)
    
    # 불펜 관리
    _reliever_idx: int = 0
    
    def get_next_reliever(self) -> Optional[PitcherStats]:
        """다음 사용 가능한 불펜 투수 반환. 소진 시 None."""
        if self._reliever_idx >= len(self.bullpen):
            return None
        reliever = self.bullpen[self._reliever_idx]
        self._reliever_idx += 1
        return reliever
```

### V0.1 팀 구성 요구사항

```
최소 구성:
  - 라인업: 9명 (DH 포함, 투수는 타석에 서지 않음)
  - 선발 투수: 1명
  - 불펜: 최소 4명 (선발 6이닝 + 불펜 각 1이닝 = 10이닝 커버)
  
  연장전 대비: 불펜이 소진되면 마지막 투수가 계속 등판 (V0.1 한계)
```

---

## 8. 경기 결과 (GameResult)

```python
@dataclass
class GameResult:
    score: dict[str, int]              # {"away": 3, "home": 5}
    winner: str                        # "away" | "home"
    innings_played: int                # 경기 이닝 수
    play_log: list[PlayEvent]          # 전체 플레이 기록
    
    # 통계 요약
    hits: dict[str, int]               # 각 팀 안타 수
    runs_by_inning: dict[str, list[int]]  # 이닝별 득점
    total_pitches: dict[str, int]      # 각 팀 투수 총 투구 수
    
    def box_score(self) -> str:
        """인간이 읽을 수 있는 박스 스코어 문자열"""
        pass
    
    def summary(self) -> dict:
        """주요 통계 요약 딕셔너리"""
        pass
```

---

## 9. Monte Carlo 시뮬레이션

```python
def simulate_series(
    away_team: Team,
    home_team: Team,
    park: ParkFactors,
    league: LeagueStats,
    n_simulations: int = 1000,
    seed: int = 42
) -> SeriesResult:
    """
    동일 매치업을 N회 시뮬레이션하여 승률 및 통계 분포를 산출.
    
    Returns:
        SeriesResult with win_pct, avg_score, score_distribution, etc.
    """
    rng = np.random.default_rng(seed)
    results = []
    
    for i in range(n_simulations):
        result = simulate_game(away_team, home_team, park, league, rng)
        results.append(result)
    
    return SeriesResult(results)


@dataclass
class SeriesResult:
    results: list[GameResult]
    
    @property
    def away_win_pct(self) -> float:
        wins = sum(1 for r in self.results if r.winner == "away")
        return wins / len(self.results)
    
    @property
    def home_win_pct(self) -> float:
        return 1.0 - self.away_win_pct
    
    @property
    def avg_total_runs(self) -> float:
        return np.mean([r.score["away"] + r.score["home"] for r in self.results])
    
    @property
    def avg_away_runs(self) -> float:
        return np.mean([r.score["away"] for r in self.results])
    
    @property
    def avg_home_runs(self) -> float:
        return np.mean([r.score["home"] for r in self.results])
    
    def score_distribution(self, side: str) -> dict[int, float]:
        """득점별 확률 분포"""
        scores = [r.score[side] for r in self.results]
        counts = Counter(scores)
        return {k: v / len(scores) for k, v in sorted(counts.items())}
    
    def summary(self) -> dict:
        return {
            "n_simulations": len(self.results),
            "away_win_pct": self.away_win_pct,
            "home_win_pct": self.home_win_pct,
            "avg_away_runs": self.avg_away_runs,
            "avg_home_runs": self.avg_home_runs,
            "avg_total_runs": self.avg_total_runs,
            "extra_innings_pct": sum(1 for r in self.results if r.innings_played > 9) / len(self.results)
        }
```

---

## 10. Manfred Runner (연장전 자동 주자)

### 규칙 (현행 MLB)

10회부터 각 하프이닝 시작 시, 무사 주자 2루 자동 배치.
배치되는 주자는 직전 이닝 마지막 아웃을 기록한 타자의 바로 앞 타순 타자.

### V0.1 단순화

```
function place_manfred_runner(state, batting_team):
    """10회+ 하프이닝 시작 시 2루에 자동 주자 배치"""
    batting_side = "away" if state.half == "top" else "home"
    batter_idx = state.batting_order_idx[batting_side]
    
    # 현재 타순의 바로 앞 타자 (타순 순환)
    runner_idx = (batter_idx - 1) % 9
    runner_player = batting_team.lineup[runner_idx]
    
    state.runners["2B"] = Runner(
        player_id=runner_player.player_id,
        name=runner_player.name,
        from_base="2B"
    )
```

---

## 11. 엣지 케이스 처리

| 케이스 | 처리 방법 |
|--------|----------|
| 불펜 소진 | 마지막 투수가 무제한 등판 (V0.1 한계) |
| 연장 20회 이상 | 최대 20이닝으로 상한. 그 이후 동점이면 무승부 처리 |
| 만루 + GO + 0아웃 | DP 판정 → DP 시 1루/2루 주자 아웃, 3루 주자 홈 득점 확률 적용 |
| 9회말 홈팀 리드 시작 | 9회말 진행하지 않음 (경기 종료) |
| 9회말 중 역전 (워크오프) | 즉시 경기 종료 (추가 타석 없음) |
| 3아웃 동시 달성 (DP + 기존 아웃) | 이닝 즉시 종료, 추가 득점 없음 |
| 주자 충돌 (두 주자가 같은 베이스) | 뒤에서부터 처리하여 방지 (resolve_runners 알고리즘) |

---

## 12. V0.1 명시적 제외 사항

| 제외 항목 | 이유 | 예정 Phase |
|----------|------|-----------|
| AI 감독의 투수 교체 결정 | Phase 1 핵심 기능 | 1 |
| 대타 / 대주자 | AI 감독 결정 + 벤치 관리 필요 | 1 |
| 도루 / 견제 | AI 감독 결정 필요 | 1 |
| 번트 | AI 감독 결정 필요 | 1 |
| 고의사구 | AI 감독 결정 필요 | 1 |
| 투수 피로 누적 효과 | 투구 수에 따른 성적 저하 모델 필요 | 1 |
| 수비 배치 / 시프트 | 수비 모델 필요 | 2 |
| 에러 (E) | 수비 모델 필요 | 0.2+ |
| 파울 아웃 / 번트 파울 | 세분화된 아웃 유형 | 0.2+ |
| 홈구장 어드밴티지 (심리적) | Park factor 외 추가 보정 | 2 |

---

## 13. 검증 기준

### 단위 테스트

```
1. 이닝 구조:
   - 3아웃 후 하프이닝 종료 확인
   - 9이닝 후 점수 차 있으면 경기 종료
   - 동점 시 연장전 진입
   - 9회말 홈팀 리드 시 9회말 스킵

2. 주자 진루:
   - HR → 모든 주자 + 타자 홈 (만루 HR = 4점)
   - BB → 포스 진루만 (1,3루에서 BB → 주자 1,2,3루, 3루 주자 잔류)
   - BB → 만루에서 BB → 밀어내기 1점
   - 싱글 → 주자 없을 때 타자 1루
   - 더블 → 주자 없을 때 타자 2루

3. 더블플레이:
   - 주자 없을 때 GO → DP 발생하지 않음
   - 2아웃일 때 GO → DP 발생하지 않음
   - 주자 1루 + 0아웃 + GO → DP 확률 적용 확인

4. 희생플라이:
   - 주자 3루 + 0아웃 + FO → SF 확률 적용 확인
   - 2아웃 + FO → SF 발생하지 않음

5. 투수 교체:
   - 선발 100구 도달 시 교체
   - 선발 6.0이닝 완료 시 교체
   - 불펜 1이닝 완료 시 교체
   - 불펜 소진 시 마지막 투수 유지

6. Manfred Runner:
   - 9이닝까지는 주자 배치 없음
   - 10회부터 무사 2루 주자 배치 확인
   - 배치 주자가 올바른 타순 확인

7. 워크오프:
   - 9회말 역전 시 즉시 종료
   - 10회말 역전 시 즉시 종료
   - 9회초 역전 시 종료하지 않음 (9회말 진행)
```

### 통합 테스트 (Sanity Check)

```
8. 득점 현실성:
   - 리그 평균 타자/투수로 1,000경기 시뮬레이션
   - 경기당 평균 총 득점: 8.0~10.0 범위 (2024 MLB 평균 ≈ 8.6)
   - 경기당 팀 평균 득점: 4.0~5.0 범위

9. 결과 분포:
   - 셧아웃 (완봉) 비율: 5~15% (2024 MLB ≈ 7%)
   - 연장전 비율: 6~12% (2024 MLB ≈ 8%)
   - 두 자릿수 득점 경기 비율: 합리적 범위

10. 홈팀 승률:
    - 동일 전력 팀 → 홈 승률 ≈ 50~54% (약간의 홈 어드밴티지는 V0.1에서 미반영이므로 ~50%)

11. 라인업 순서 효과:
    - 강타자를 3~4번에 배치한 팀 vs 랜덤 배치 → 약간의 득점 차이 확인

12. Monte Carlo 수렴:
    - 1,000회 vs 10,000회 시뮬레이션 결과의 승률 차이 < 2%
```

---

## 14. 구현 노트 (Claude Code용)

### 디렉토리 구조 (0-B 확장)

```
dugout/
├── engine/
│   ├── __init__.py
│   ├── at_bat.py              # Phase 0-B (구현 완료)
│   ├── models.py              # 데이터 클래스 (확장)
│   ├── constants.py           # 매직 넘버 (확장)
│   ├── game.py                # 이 스펙의 핵심: 경기 시뮬레이션
│   ├── runners.py             # 주자 진루 모델
│   ├── pitching.py            # 투수 교체 로직
│   └── monte_carlo.py         # Monte Carlo 시뮬레이션 + 결과 분석
├── data/
│   ├── __init__.py
│   ├── loader.py              # Phase 0-A에서 정의
│   └── runner_tables.py       # 주자 진루 확률 테이블 (상수)
├── tests/
│   ├── test_at_bat.py         # Phase 0-B (완료)
│   ├── test_runners.py        # 주자 진루 테스트
│   ├── test_game.py           # 경기 흐름 테스트
│   ├── test_pitching.py       # 투수 교체 테스트
│   ├── test_monte_carlo.py    # MC 시뮬레이션 테스트
│   └── test_sanity.py         # 통합 sanity check
└── notebooks/
    └── explore.ipynb
```

### 핵심 원칙

1. **주자 진루 확률 테이블은 별도 파일로 분리 (`runner_tables.py`).**
   나중에 실제 데이터로 교체할 때 이 파일만 바꾸면 됨.

2. **GameState는 불변성을 최대한 유지.**
   각 플레이마다 상태를 직접 변경하지만, play_log에 before/after를 기록하여 추적 가능.

3. **resolve 함수들은 순수 함수에 가깝게 설계.**
   `resolve_runners(event, runners, outs, rng)` → 입력이 같으면 (같은 rng 상태에서) 같은 출력.

4. **테스트 우선:** 먼저 test_runners.py의 단위 테스트를 통과시킨 후 game.py에 통합.

5. **box_score() 출력 포맷:**
   ```
              1  2  3  4  5  6  7  8  9    R  H  E
   Yankees    0  1  0  0  2  0  0  1  0 —  4  8  0
   Red Sox    1  0  0  3  0  0  0  0  X —  4  7  0
   ```
   이 포맷은 디버깅과 결과 확인에 필수.

---

## 부록 A: 확률 테이블 요약

모든 확률값은 리그 평균 근사치이며, Phase 0-A에서 실제 데이터 기반으로 업데이트 예정.

### 안타 시 진루 확률 요약

```
1B (싱글):
  1루 주자 → 2루(.40) / 3루(.50) / 홈(.10)
  2루 주자 → 3루(.30) / 홈(.70)
  3루 주자 → 홈(.95) / 잔류(.05)

2B (더블):
  1루 주자 → 3루(.45) / 홈(.55)
  2루 주자 → 홈(.95) / 3루(.05)
  3루 주자 → 홈(1.00)

3B (트리플):
  모든 주자 → 홈(1.00)

HR (홈런):
  모든 주자 + 타자 → 홈(1.00)

BB/HBP:
  포스 진루만
```

### 아웃 시 확률 요약

```
GO:
  DP 확률 (적격 상황): 0.55
  DP 시 3루 주자 홈 득점: 0.50
  일반 GO:
    1루 주자 → 2루(.70) / 잔류(.30)
    2루 주자 → 3루(.55) / 잔류(.45)
    3루 주자 (아웃<2) → 홈(.50) / 잔류(.50)

FO:
  SF 확률 (적격 상황): 0.65
  태그업:
    1루 주자 → 2루(.10) / 잔류(.90)
    2루 주자 → 3루(.35) / 잔류(.65)
```

---

## 부록 B: 예시 하프이닝 시뮬레이션

### 상황: 1회초, 어웨이팀 공격

```
초기 상태: 이닝=1, half=top, outs=0, runners={}, score=0-0

타석 1: 1번 타자 vs 선발투수
  → 결과: 1B (싱글)
  → 주자: {1B: 1번타자}
  → outs=0, score=0-0

타석 2: 2번 타자
  → 결과: GO (땅볼)
  → DP 적격? 아웃<2, 1루 주자 있음 → Yes
  → DP 판정: rng=0.62 > 0.55 → DP 아님, 일반 GO
  → 1루 주자 진루: rng=0.35 → 2루(.70 범위) → 2루로
  → 주자: {2B: 1번타자}
  → outs=1, score=0-0

타석 3: 3번 타자
  → 결과: 2B (더블)
  → 2루 주자 진루: rng=0.12 → 홈(.95 범위) → 득점!
  → 타자 → 2루
  → 주자: {2B: 3번타자}
  → outs=1, score=1-0

타석 4: 4번 타자
  → 결과: K (삼진)
  → 주자 변동 없음
  → outs=2, score=1-0

타석 5: 5번 타자
  → 결과: FO (뜬공)
  → SF 적격? 아웃<2 아님 (outs=2) → No
  → outs=3, score=1-0

하프이닝 종료. 어웨이팀 1점.
다음 타석: 6번 타자부터 (1회말 종료 후 2회초)
```
