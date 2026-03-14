# Dugout — Phase 0-B: 타석 확률 모델 스펙

> **Version:** 0.1.0
> **Status:** Draft
> **Author:** JJ + Luca
> **Date:** 2026-03-12

---

## 1. 목적

투수-타자 매치업이 주어졌을 때, 해당 타석의 결과를 확률 분포로 산출하는 모델.
이 모듈은 Dugout 시뮬레이션 엔진의 최소 단위이며, 모든 상위 시뮬레이션(경기, 시즌)의 기반이 된다.

---

## 2. 이벤트 카테고리

### V0.1 이벤트 (9개)

| Code | 이벤트 | 설명 |
|------|--------|------|
| `K` | Strikeout | 삼진 |
| `BB` | Walk | 볼넷 |
| `HBP` | Hit By Pitch | 사구 |
| `1B` | Single | 1루타 |
| `2B` | Double | 2루타 |
| `3B` | Triple | 3루타 |
| `HR` | Home Run | 홈런 |
| `GO` | Ground Out | 땅볼 아웃 (Line out 중 일부 흡수) |
| `FO` | Fly Out | 뜬공 아웃 (Line out 중 일부 흡수) |

**제약:** 모든 이벤트의 확률 합 = 1.0

### V0.2+ 확장 예정

| Code | 이벤트 | 확장 이유 |
|------|--------|----------|
| `LO` | Line Out | 타구 유형별 더블플레이 확률 차이 반영 |
| `E` | Error | 수비력 모델링, 팀별 수비 성적 반영 |
| `DP` | Double Play | 명시적 DP 확률 (현재는 GO 내에서 상황별 확률로 처리) |
| `SAC` | Sacrifice (Bunt/Fly) | AI 감독의 전략적 선택과 연동 (Phase 1) |
| `IBB` | Intentional Walk | AI 감독의 전략적 선택과 연동 (Phase 1) |

---

## 3. 확률 모델: 2단계 접근 (Two-Stage Model)

야구의 물리적 구조를 반영하여, 타석 결과를 두 단계로 분리하여 산출한다.

### 3.1 Stage 1: Plate Discipline (스트라이크존 결과)

투수와 타자의 **삼진/볼넷 능력**에 의해 결정되는 단계.

4가지 상위 카테고리의 확률을 산출:

```
P(K)   — 삼진 확률
P(BB)  — 볼넷 확률
P(HBP) — 사구 확률
P(BIP) — Ball In Play 확률 = 1 - P(K) - P(BB) - P(HBP)
```

**결합 방법: Log5**

각 이벤트 `e`에 대해:

```
p_bat_e = 타자의 해당 이벤트 비율 (PA 기준)
p_pit_e = 투수의 해당 이벤트 피허용 비율 (PA 기준)
p_lg_e  = 리그 평균 해당 이벤트 비율 (PA 기준)

odds_bat = p_bat_e / (1 - p_bat_e)
odds_pit = p_pit_e / (1 - p_pit_e)
odds_lg  = p_lg_e / (1 - p_lg_e)

odds_combined = odds_bat * odds_pit / odds_lg

p_combined_e = odds_combined / (1 + odds_combined)
```

K, BB, HBP 각각에 Log5 적용 후, BIP = 1 - K - BB - HBP.

**정규화:** Log5 적용 후 K + BB + HBP > 1이 되는 극단적 케이스가 (이론적으로) 가능.
이 경우 K, BB, HBP를 비율 유지하며 합이 최대 0.95가 되도록 정규화 (BIP 최소 5% 보장).

### 3.2 Stage 2: Batted Ball Outcome (인플레이 결과)

BIP가 발생했을 때, 그 타구의 결과를 결정하는 단계.

6가지 결과의 **조건부 확률**을 산출:

```
P(1B | BIP)
P(2B | BIP)
P(3B | BIP)
P(HR | BIP)
P(GO | BIP)
P(FO | BIP)

합 = 1.0
```

**결합 방법: 타자 중심 + 투수 GB/FB 보정**

이 단계에서는 타자의 타구 특성이 지배적이라는 FIP 철학을 따른다.

```
1. 타자의 BIP 내 결과 분포를 기본값(base)으로 사용:
   base_e = 타자의 P(e | BIP)  (e = 1B, 2B, 3B, HR, GO, FO)

2. 투수의 GB/FB ratio로 GO/FO 비율 보정:
   gb_fb_adj = 투수의 (GO/FO ratio) / 리그 평균 (GO/FO ratio)
   
   adj_GO = base_GO * gb_fb_adj
   adj_FO = base_FO / gb_fb_adj
   (나머지 안타 유형은 유지)

3. 투수의 HR 허용률로 HR 보정:
   hr_adj = 투수의 P(HR|BIP) / 리그 평균 P(HR|BIP)
   adj_HR = base_HR * hr_adj
   (HR 증감분은 FO에서 차감/추가 — 홈런은 "나가지 않은 플라이볼"의 변환)

4. 정규화: 6개 확률의 합이 1이 되도록 조정
```

### 3.3 최종 확률 산출

```
P(K)   = Stage 1에서 산출
P(BB)  = Stage 1에서 산출
P(HBP) = Stage 1에서 산출
P(1B)  = P(BIP) × P(1B | BIP)
P(2B)  = P(BIP) × P(2B | BIP)
P(3B)  = P(BIP) × P(3B | BIP)
P(HR)  = P(BIP) × P(HR | BIP)
P(GO)  = P(BIP) × P(GO | BIP)
P(FO)  = P(BIP) × P(FO | BIP)

검증: 9개 확률의 합 = 1.0 (부동소수점 허용 오차 1e-9)
```

---

## 4. Platoon Split (좌우 분할)

투수-타자의 좌/우 조합에 따라 성적이 크게 달라진다.

### 적용 방법

타자와 투수의 통계를 전체 성적 대신 **해당 좌/우 분할 성적**으로 사용.

```
매치업 조합:
  RHP vs RHB → 타자의 vs RHP 성적, 투수의 vs RHB 성적
  RHP vs LHB → 타자의 vs RHP 성적, 투수의 vs LHB 성적
  LHP vs RHB → 타자의 vs LHP 성적, 투수의 vs RHB 성적
  LHP vs LHB → 타자의 vs LHP 성적, 투수의 vs LHB 성적
```

### 소표본 보정 (Regression to Mean)

분할 성적은 표본이 작을 수 있다 (좌완 투수를 상대한 타석 수가 적은 우타자 등).

```
유효 타석 수 기준:
  n = 해당 분할의 PA 수
  n_min = 100  (이 이상이면 분할 성적 100% 사용)
  
  weight = min(n / n_min, 1.0)
  
  adjusted_stat = weight × split_stat + (1 - weight) × overall_stat
```

n_min = 100은 초기값이며, 검증 결과에 따라 조정 가능.

---

## 5. Park Factor

구장별로 이벤트 발생 빈도가 다르다 (쿠어스 필드의 HR, 페트코 파크의 K 등).

### 적용 방법

FanGraphs의 **이벤트별 park factor**를 사용 (100 = 중립).

```
적용 대상 이벤트: HR, 2B, 3B, 1B
적용하지 않는 이벤트: K, BB, HBP (투수-타자 능력 중심, 구장 영향 미미)
적용하지 않는 이벤트: GO, FO (아웃 유형은 구장보다 선수 특성)

보정 공식 (Stage 2 BIP 결과에 적용):
  pf_e = 해당 구장의 이벤트 e park factor / 100
  
  adj_P(e | BIP) = raw_P(e | BIP) × pf_e

보정 후 정규화하여 합 = 1.0 유지
```

### 데이터 소스

```python
# pybaseball에서 park factor 접근
# FanGraphs Guts! 페이지 또는 팀 페이지에서 구장 보정 데이터 수집
# 구체적 접근 방법은 0-A 데이터 파이프라인 스펙에서 정의
```

---

## 6. 입력 데이터 요구사항

이 모델이 요구하는 최소 데이터 필드. (정확한 스키마와 소스는 Phase 0-A에서 정의)

### 타자 데이터 (per player, per season)

| 필드 | 설명 | 용도 |
|------|------|------|
| `pa` | Plate Appearances | 분모 |
| `k_rate` | K / PA | Stage 1 |
| `bb_rate` | BB / PA | Stage 1 |
| `hbp_rate` | HBP / PA | Stage 1 |
| `bip` | Balls In Play 수 | Stage 2 분모 |
| `1b_rate_bip` | 1B / BIP | Stage 2 |
| `2b_rate_bip` | 2B / BIP | Stage 2 |
| `3b_rate_bip` | 3B / BIP | Stage 2 |
| `hr_rate_bip` | HR / BIP | Stage 2 |
| `go_rate_bip` | GO / BIP | Stage 2 |
| `fo_rate_bip` | FO / BIP | Stage 2 |
| `hand` | 타석 (L/R/S) | Platoon split |
| `k_rate_vs_lhp` | vs LHP K rate | Platoon |
| `k_rate_vs_rhp` | vs RHP K rate | Platoon |
| `bb_rate_vs_lhp` | vs LHP BB rate | Platoon |
| `bb_rate_vs_rhp` | vs RHP BB rate | Platoon |
| `pa_vs_lhp` | PA vs LHP | Platoon 소표본 보정 |
| `pa_vs_rhp` | PA vs RHP | Platoon 소표본 보정 |

*참고: 분할 성적의 모든 rate 필드도 필요하지만, 위에는 대표적인 것만 기재. 전체 목록은 0-A에서 정의.*

### 투수 데이터 (per player, per season)

| 필드 | 설명 | 용도 |
|------|------|------|
| `pa_against` | 상대한 총 PA | 분모 |
| `k_rate` | K / PA | Stage 1 |
| `bb_rate` | BB / PA | Stage 1 |
| `hbp_rate` | HBP / PA | Stage 1 |
| `hr_rate_bip` | HR / BIP | Stage 2 HR 보정 |
| `go_fo_ratio` | GO / FO | Stage 2 GB/FB 보정 |
| `hand` | 투구 손 (L/R) | Platoon split |
| `k_rate_vs_lhb` | vs LHB K rate | Platoon |
| `k_rate_vs_rhb` | vs RHB K rate | Platoon |
| `bb_rate_vs_lhb` | vs LHB BB rate | Platoon |
| `bb_rate_vs_rhb` | vs RHB BB rate | Platoon |
| `pa_vs_lhb` | PA vs LHB | Platoon 소표본 보정 |
| `pa_vs_rhb` | PA vs RHB | Platoon 소표본 보정 |

### 리그 평균 데이터 (per season)

| 필드 | 설명 |
|------|------|
| `lg_k_rate` | 리그 평균 K/PA |
| `lg_bb_rate` | 리그 평균 BB/PA |
| `lg_hbp_rate` | 리그 평균 HBP/PA |
| `lg_1b_rate_bip` | 리그 평균 1B/BIP |
| `lg_2b_rate_bip` | 리그 평균 2B/BIP |
| `lg_3b_rate_bip` | 리그 평균 3B/BIP |
| `lg_hr_rate_bip` | 리그 평균 HR/BIP |
| `lg_go_rate_bip` | 리그 평균 GO/BIP |
| `lg_fo_rate_bip` | 리그 평균 FO/BIP |
| `lg_go_fo_ratio` | 리그 평균 GO/FO ratio |

### Park Factor 데이터 (per ballpark)

| 필드 | 설명 |
|------|------|
| `pf_1b` | 1B park factor (100 = neutral) |
| `pf_2b` | 2B park factor |
| `pf_3b` | 3B park factor |
| `pf_hr` | HR park factor |

---

## 7. 모듈 인터페이스

### 함수 시그니처

```python
def simulate_at_bat(
    batter: BatterStats,
    pitcher: PitcherStats,
    league: LeagueStats,
    park: ParkFactors,
    rng: np.random.Generator  # 재현 가능한 랜덤
) -> AtBatResult:
    """
    단일 타석을 시뮬레이션하여 결과를 반환.
    
    Returns:
        AtBatResult with .event (str) and .probabilities (dict)
    """
    pass


def calculate_matchup_probabilities(
    batter: BatterStats,
    pitcher: PitcherStats,
    league: LeagueStats,
    park: ParkFactors
) -> dict[str, float]:
    """
    투수-타자 매치업의 이벤트별 확률 분포를 산출.
    시뮬레이션 없이 확률만 반환 (분석/디버깅용).
    
    Returns:
        {"K": 0.22, "BB": 0.08, "HBP": 0.01, "1B": 0.15, ...}
        합 = 1.0
    """
    pass
```

### 데이터 클래스 (초안)

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class BatterStats:
    player_id: str
    name: str
    hand: str                  # "L", "R", "S" (switch)
    pa: int
    k_rate: float
    bb_rate: float
    hbp_rate: float
    # BIP 결과 (조건부 확률, 합 = 1.0)
    single_rate_bip: float
    double_rate_bip: float
    triple_rate_bip: float
    hr_rate_bip: float
    go_rate_bip: float
    fo_rate_bip: float
    # Platoon splits (Optional — 없으면 overall 사용)
    splits: Optional[dict] = None
    # splits = {
    #   "vs_LHP": {"pa": int, "k_rate": float, "bb_rate": float, ...},
    #   "vs_RHP": {"pa": int, "k_rate": float, "bb_rate": float, ...}
    # }

@dataclass
class PitcherStats:
    player_id: str
    name: str
    hand: str                  # "L", "R"
    pa_against: int
    k_rate: float
    bb_rate: float
    hbp_rate: float
    hr_rate_bip: float
    go_fo_ratio: float
    # Platoon splits (Optional)
    splits: Optional[dict] = None

@dataclass
class LeagueStats:
    season: int
    k_rate: float
    bb_rate: float
    hbp_rate: float
    single_rate_bip: float
    double_rate_bip: float
    triple_rate_bip: float
    hr_rate_bip: float
    go_rate_bip: float
    fo_rate_bip: float
    go_fo_ratio: float

@dataclass
class ParkFactors:
    park_name: str
    pf_1b: float    # 100 = neutral
    pf_2b: float
    pf_3b: float
    pf_hr: float

@dataclass
class AtBatResult:
    event: str                          # "K", "BB", "1B", "HR", etc.
    probabilities: dict[str, float]     # 전체 확률 분포 (디버깅/분석용)
```

---

## 8. 알고리즘 의사코드

```
function calculate_matchup_probabilities(batter, pitcher, league, park):
    
    # === Platoon 처리 ===
    bat_stats = resolve_platoon(batter, pitcher.hand)
    pit_stats = resolve_platoon(pitcher, batter.effective_hand(pitcher.hand))
    
    # === Stage 1: Plate Discipline ===
    p_k   = log5(bat_stats.k_rate,   pit_stats.k_rate,   league.k_rate)
    p_bb  = log5(bat_stats.bb_rate,  pit_stats.bb_rate,  league.bb_rate)
    p_hbp = log5(bat_stats.hbp_rate, pit_stats.hbp_rate, league.hbp_rate)
    
    # 정규화: K + BB + HBP가 0.95를 초과하면 비율 유지하며 축소
    total_non_bip = p_k + p_bb + p_hbp
    if total_non_bip > 0.95:
        scale = 0.95 / total_non_bip
        p_k   *= scale
        p_bb  *= scale
        p_hbp *= scale
    
    p_bip = 1.0 - p_k - p_bb - p_hbp
    
    # === Stage 2: Batted Ball Outcome ===
    # 타자의 BIP 내 분포를 base로
    base = {
        "1B": bat_stats.single_rate_bip,
        "2B": bat_stats.double_rate_bip,
        "3B": bat_stats.triple_rate_bip,
        "HR": bat_stats.hr_rate_bip,
        "GO": bat_stats.go_rate_bip,
        "FO": bat_stats.fo_rate_bip
    }
    
    # 투수의 GB/FB 보정
    gb_fb_adj = pit_stats.go_fo_ratio / league.go_fo_ratio
    base["GO"] *= gb_fb_adj
    base["FO"] /= gb_fb_adj
    
    # 투수의 HR 보정
    hr_adj = pit_stats.hr_rate_bip / league.hr_rate_bip
    hr_delta = base["HR"] * (hr_adj - 1.0)
    base["HR"] += hr_delta
    base["FO"] -= hr_delta    # HR 증감은 FO에서 보상
    base["FO"] = max(base["FO"], 0.01)  # FO가 음수 방지
    
    # Park Factor 보정
    base["1B"] *= park.pf_1b / 100
    base["2B"] *= park.pf_2b / 100
    base["3B"] *= park.pf_3b / 100
    base["HR"] *= park.pf_hr / 100
    
    # 정규화: BIP 내 확률 합 = 1.0
    bip_total = sum(base.values())
    for key in base:
        base[key] /= bip_total
    
    # === 최종 확률 ===
    result = {
        "K":   p_k,
        "BB":  p_bb,
        "HBP": p_hbp,
        "1B":  p_bip * base["1B"],
        "2B":  p_bip * base["2B"],
        "3B":  p_bip * base["3B"],
        "HR":  p_bip * base["HR"],
        "GO":  p_bip * base["GO"],
        "FO":  p_bip * base["FO"]
    }
    
    # 최종 검증
    assert abs(sum(result.values()) - 1.0) < 1e-9
    
    return result


function log5(p_bat, p_pit, p_lg):
    """Log5 확률 결합"""
    odds_bat = p_bat / (1 - p_bat)
    odds_pit = p_pit / (1 - p_pit)
    odds_lg  = p_lg  / (1 - p_lg)
    
    odds_combined = odds_bat * odds_pit / odds_lg
    return odds_combined / (1 + odds_combined)


function resolve_platoon(player, opponent_hand):
    """좌우 분할 성적 적용 (소표본 보정 포함)"""
    if player.splits is None:
        return player  # 분할 데이터 없으면 overall 사용
    
    split_key = f"vs_{opponent_hand}HP"  # "vs_LHP" or "vs_RHP"
    split = player.splits.get(split_key)
    
    if split is None:
        return player
    
    n = split["pa"]
    n_min = 100
    weight = min(n / n_min, 1.0)
    
    # weight 비율로 split과 overall 성적 혼합
    # (각 rate 필드에 대해 동일하게 적용)
    blended = blend_stats(player, split, weight)
    return blended


function simulate_at_bat(batter, pitcher, league, park, rng):
    """확률 분포에서 랜덤 샘플링으로 결과 결정"""
    probs = calculate_matchup_probabilities(batter, pitcher, league, park)
    
    events = list(probs.keys())
    weights = list(probs.values())
    
    result_event = rng.choice(events, p=weights)
    
    return AtBatResult(event=result_event, probabilities=probs)
```

---

## 9. 엣지 케이스 처리

| 케이스 | 처리 방법 |
|--------|----------|
| 선수 데이터 없음 (신인, 콜업 등) | 리그 평균 사용 (해당 포지션 평균이면 더 좋음) |
| PA < 50 (극소 표본) | 리그 평균으로 강하게 회귀: weight = PA / 200 |
| 스위치 히터 (S) | 상대 투수 손에 따라 반대 타석 사용 (vs RHP → 좌타, vs LHP → 우타) |
| Park factor 데이터 없음 | 모든 park factor = 100 (중립 가정) |
| 확률이 음수가 되는 경우 | 해당 이벤트 확률을 0.001로 floor 처리 후 정규화 |
| K% 또는 BB%가 0인 투수/타자 | 0.001로 floor (Log5에서 0은 odds 계산 불가) |

---

## 10. V0.1 명시적 제외 사항

다음은 V0.1에서 **의도적으로 구현하지 않는** 기능이다. Phase 1 이후로 미룸.

| 제외 항목 | 이유 | 예정 Phase |
|----------|------|-----------|
| 도루 (Stolen Base) | AI 감독 결정이 필요 (Phase 1) | 1 |
| 번트 (Bunt) | AI 감독 결정이 필요 | 1 |
| 고의사구 (IBB) | AI 감독 결정이 필요 | 1 |
| 투수 피로 / 구수 | 불펜 관리 시스템 필요 | 1 |
| 수비 시프트 | Statcast 수비 데이터 통합 필요 | 2 |
| 구종별 매치업 | Statcast pitch-level 데이터 필요 | 2 |
| 날씨 보정 | 날씨 API 연동 필요 | 3 |
| 심판 보정 | 심판별 스트라이크존 데이터 필요 | 2+ |
| 다년 가중평균 (Marcel) | 단일 시즌으로 시작, 이후 확장 | 1 |
| Error (E) | 수비력 모델 필요 | 0.2+ |
| Line Out (LO) | GO/FO에 흡수. 향후 분리 | 0.2+ |

---

## 11. 검증 기준

이 모델의 "정확함"을 판단하는 기준. (구체적 검증 프레임워크는 Phase 0-E에서 정의)

### 단위 테스트

```
1. 확률 합 검증: 모든 매치업에서 9개 이벤트 확률 합 = 1.0 (±1e-9)

2. 방향성 검증 (Sanity Check):
   - 고삼진 투수 (K% > 30%) vs 평균 타자 → P(K)가 리그 평균보다 높아야 함
   - 파워 히터 (ISO > .250) vs 평균 투수 → P(HR)이 리그 평균보다 높아야 함
   - 쿠어스 필드 → P(HR), P(2B)가 중립 구장보다 높아야 함
   - 좌완 투수 vs 좌타자 → P(K)가 좌완 vs 우타자보다 높아야 함 (일반적으로)

3. 범위 검증:
   - 모든 개별 확률: 0.001 ≤ P(e) ≤ 0.95
   - P(K): 0.05 ~ 0.50 범위
   - P(BB): 0.02 ~ 0.25 범위
   - P(HR): 0.001 ~ 0.15 범위

4. 리그 평균 복원:
   - 모든 타자 × 모든 투수 매치업의 가중 평균 ≈ 리그 평균 이벤트 분포 (±2%)
```

### 통합 테스트 (경기 시뮬레이션 이후)

```
5. 2024 시즌 팀별 득점 비교:
   - 각 팀의 시뮬레이션 평균 득점 vs 실제 득점: 상관계수 > 0.85

6. 개인 성적 복원:
   - 주요 타자 (PA > 500)의 시뮬레이션 평균 wOBA vs 실제 wOBA: RMSE < 0.030
```

---

## 12. 구현 노트 (Claude Code용)

### 디렉토리 구조 제안

```
dugout/
├── engine/
│   ├── __init__.py
│   ├── at_bat.py          # 이 스펙의 핵심 구현
│   ├── models.py          # 데이터 클래스 (BatterStats, PitcherStats, etc.)
│   └── constants.py       # 매직 넘버 (n_min, floor값 등)
├── data/
│   ├── __init__.py
│   └── loader.py          # Phase 0-A에서 정의
├── tests/
│   ├── test_at_bat.py     # 단위 테스트
│   └── test_sanity.py     # 방향성 검증
└── notebooks/
    └── explore.ipynb      # 탐색/디버깅용
```

### 핵심 원칙

1. **재현 가능성:** `np.random.Generator`를 외부에서 주입. 시드 고정으로 동일 결과 보장.
2. **확률 투명성:** `simulate_at_bat`은 항상 선택된 결과와 함께 전체 확률 분포를 반환.
3. **방어적 코딩:** 모든 확률 계산 후 합이 1.0인지 assert. 음수/NaN 체크.
4. **상수 분리:** n_min, floor값, 최대 non-BIP 비율 등을 constants.py에 모아서 튜닝 가능하게.

---

## 부록 A: Log5 수학적 배경

Tom Tango의 Log5 method는 두 확률을 리그 맥락에서 결합하는 표준 방법이다.

직관: 타자의 삼진율이 25%이고 투수의 삼진율이 30%일 때, 리그 평균이 22%라면,
이 매치업의 삼진율은 단순 평균(27.5%)이 아니라, 두 선수가 각각 리그 평균 대비
얼마나 더/덜 삼진을 유발하는지의 **승법적 결합**이다.

```
Log5 공식 유도:
  
  Odds(bat) = p_bat / (1 - p_bat)
  Odds(pit) = p_pit / (1 - p_pit)  
  Odds(lg)  = p_lg / (1 - p_lg)

  Odds(combined) = Odds(bat) × Odds(pit) / Odds(lg)

  P(combined) = Odds(combined) / (1 + Odds(combined))

이는 로지스틱 공간에서의 선형 결합과 동치:
  logit(combined) = logit(bat) + logit(pit) - logit(lg)
```

참고: Tango, Lichtman, Dolphin — "The Book: Playing the Percentages in Baseball" (2007)

---

## 부록 B: 예시 계산

### 예시: Aaron Judge vs Gerrit Cole (가상 데이터)

```
입력:
  Judge: K%=25.3%, BB%=14.1%, HBP%=1.2%, hand=R
         BIP 분포: 1B=30%, 2B=12%, 3B=1%, HR=18%, GO=22%, FO=17%
  
  Cole:  K%=29.8%, BB%=5.8%, HBP%=0.8%, hand=R
         HR/BIP=8.5%, GO/FO ratio=0.82
  
  League: K%=22.4%, BB%=8.5%, HBP%=1.0%
          HR/BIP=9.2%, GO/FO ratio=1.10
  
  Park: Yankee Stadium — pf_hr=110, pf_2b=95, pf_3b=90, pf_1b=100

Stage 1 (Log5):
  P(K)  = log5(0.253, 0.298, 0.224) = 0.323  (높은 K 매치업)
  P(BB) = log5(0.141, 0.058, 0.085) = 0.094
  P(HBP)= log5(0.012, 0.008, 0.010) = 0.010
  P(BIP)= 1 - 0.323 - 0.094 - 0.010 = 0.573

Stage 2:
  Base (Judge BIP): 1B=.300, 2B=.120, 3B=.010, HR=.180, GO=.220, FO=.170
  
  GB/FB adj: 0.82 / 1.10 = 0.745
  → GO: .220 × 0.745 = .164
  → FO: .170 / 0.745 = .228
  
  HR adj: 0.085 / 0.092 = 0.924
  → HR delta: .180 × (0.924 - 1) = -.014
  → HR: .180 - .014 = .166
  → FO: .228 + .014 = .242
  
  Park: 1B: .300×1.00=.300, 2B: .120×0.95=.114, 3B: .010×0.90=.009, HR: .166×1.10=.183
  
  정규화 전 합: .300+.114+.009+.183+.164+.242 = 1.012
  정규화 후: 1B=.296, 2B=.113, 3B=.009, HR=.181, GO=.162, FO=.239

최종:
  K=.323, BB=.094, HBP=.010
  1B=.170, 2B=.065, 3B=.005, HR=.104, GO=.093, FO=.137

  합 = 1.001 ≈ 1.0 ✓
```

이 결과의 직관적 검증:
- K% 32.3% — 두 선수 모두 삼진이 많으므로 합리적
- HR = 10.4% — Judge의 파워 + 양키 스타디움 보정 반영
- BB% 9.4% — Judge의 높은 선구안이지만 Cole의 낮은 BB 허용으로 억제
