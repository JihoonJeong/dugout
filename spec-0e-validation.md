# Dugout — Phase 0-E: 검증 프레임워크 스펙

> **Version:** 0.1.0
> **Status:** Draft
> **Author:** JJ + Luca
> **Date:** 2026-03-12
> **의존성:** Phase 0-B (타석 확률 모델), Phase 0-CD (게임 시뮬레이션), Phase 0-A (데이터 파이프라인)

---

## 1. 목적

Dugout 시뮬레이션 엔진의 정확도를 **정량적으로 측정**하는 프레임워크.
"모델이 맞다"는 감이 아니라 숫자로 판단하고, 개선 방향을 수치로 추적한다.

### 측정 대상 (4개 레벨)

| 레벨 | 대상 | 질문 |
|------|------|------|
| L1 | 타석 확률 모델 | 개별 선수의 예측 성적이 실제와 얼마나 가까운가? |
| L2 | 경기 시뮬레이션 | 팀 득점이 현실적인가? |
| L3 | 경기 예측 | 승률 예측이 실제 결과와 얼마나 일치하는가? |
| L4 | 시즌 예측 | 팀별 시즌 승수 예측이 실제와 얼마나 가까운가? |

---

## 2. Ground Truth 데이터

### 2024 시즌 실제 결과

```python
@dataclass
class ActualResults:
    season: int
    
    # 개별 선수 실제 성적 (L1 검증)
    batter_actuals: dict[str, dict]     # player_id → {"pa": int, "k_rate": float, "bb_rate": float, "woba": float, ...}
    pitcher_actuals: dict[str, dict]    # player_id → {"ip": float, "k_rate": float, "era": float, "fip": float, ...}
    
    # 팀 실제 성적 (L2, L4 검증)
    team_actuals: dict[str, dict]       # team_id → {"wins": int, "losses": int, "runs_scored": int, "runs_allowed": int, ...}
    
    # 경기별 실제 결과 (L3 검증)
    game_actuals: list[dict]            # [{"date": str, "away": str, "home": str, "away_score": int, "home_score": int, ...}]
```

### 데이터 소스

```
개별 선수:
  - pybaseball batting_stats(2024) / pitching_stats(2024)
  - 이미 0-A에서 추출된 데이터에서 actual rate를 별도 보존

팀 성적:
  - pybaseball team_batting(2024), team_pitching(2024)
  - 또는 Baseball Reference standings

경기별 결과:
  - pybaseball schedule_and_record(2024, team) 또는 MLB Stats API
  - 2,430경기 (30팀 × 162경기 / 2)
```

---

## 3. L1: 타석 확률 모델 검증

### 3.1 개별 선수 성적 비교

모델이 산출하는 확률 분포와, 선수의 실제 성적을 비교.

**대상:** PA ≥ 200인 타자 (약 300명), PA ≥ 100 상대한 투수 (약 200명)

#### 타자 메트릭

```
각 타자에 대해:
  1. 모델이 산출하는 "리그 평균 투수 상대" 확률 분포 계산
     probs = calculate_matchup_probabilities(batter, league_avg_pitcher, league, neutral_park)
  
  2. 모델 예측 rate vs 실제 rate 비교:
     - K%:  probs["K"]  vs actual_k_rate
     - BB%: probs["BB"] vs actual_bb_rate
     - HR%: probs["HR"] vs actual_hr_rate  (HR/PA)
     - wOBA: 확률 분포에서 wOBA 역산 vs 실제 wOBA
```

#### wOBA 역산

```python
def predicted_woba(probs: dict[str, float]) -> float:
    """
    확률 분포에서 wOBA를 역산.
    wOBA 가중치 (2024 기준, FanGraphs Guts!):
    """
    weights = {
        "BB":  0.690,
        "HBP": 0.722,
        "1B":  0.883,
        "2B":  1.244,
        "3B":  1.569,
        "HR":  2.004,
    }
    
    # wOBA = (가중 합) / PA
    # 확률 분포가 이미 PA 기준이므로 직접 적용 가능
    woba = sum(probs.get(event, 0) * weight for event, weight in weights.items())
    return woba
```

#### 목표 메트릭

| 메트릭 | 산출 방법 | V0.1 목표 | 의미 |
|--------|----------|-----------|------|
| K% RMSE | √(mean((pred_k - actual_k)²)) | < 0.040 | 삼진율 예측 오차 4%p 이내 |
| BB% RMSE | √(mean((pred_bb - actual_bb)²)) | < 0.030 | 볼넷율 예측 오차 3%p 이내 |
| HR/PA RMSE | √(mean((pred_hr - actual_hr)²)) | < 0.015 | 홈런율 예측 오차 1.5%p 이내 |
| wOBA RMSE | √(mean((pred_woba - actual_woba)²)) | < 0.030 | wOBA 예측 오차 30포인트 이내 |
| wOBA 상관계수 | corr(pred_woba, actual_woba) | > 0.80 | 순위 유지 능력 |

*참고: 이 목표는 "리그 평균 투수 상대" 확률과 실제 성적 비교.
실제로 선수는 다양한 투수를 상대하므로, 이 비교의 정밀도에는 본질적 한계가 있음.
wOBA 상관계수 > 0.80이면 V0.1으로서 충분.*

### 3.2 리그 평균 복원 검증

```
전체 타자의 PA 가중평균 확률 분포 ≈ 리그 평균 이벤트 분포

산출:
  weighted_avg_k = Σ(batter_pa × pred_k) / Σ(batter_pa)
  
비교:
  |weighted_avg_k - league.k_rate| < 0.005  (0.5%p 이내)
  각 이벤트에 대해 동일 검증
```

### 3.3 데이터 파이프라인 정확도 (부수 검증)

0-A 파이프라인이 실제 데이터를 얼마나 정확히 변환하는지도 여기서 측정.

```
대상: 알려진 선수 스팟 체크 (20명)

각 선수에 대해:
  파이프라인 산출 rate vs Baseball Reference 공식 기록 비교
  
  허용 오차:
  - K%, BB%: ±1.0%p
  - HR, H, 2B, 3B: ±2개 (raw count)
  - Hand: 100% 일치
  
  현재 알려진 괴리:
  - Judge BB% 18.9 vs 실제 15.0 → 원인 특정 필요 (IBB 포함? PA 범위?)
```

---

## 4. L2: 경기 시뮬레이션 검증

### 4.1 팀별 득점 비교

각 팀의 시뮬레이션 평균 득점 vs 실제 시즌 평균 득점.

```
방법:
  각 팀에 대해:
    1. 해당 팀 라인업/선발투수로 리그 평균 상대팀과 1,000경기 시뮬레이션
    2. 시뮬레이션 평균 득점 산출
    3. 실제 2024 시즌 평균 득점과 비교
  
  메트릭:
    - 30개 팀 runs_scored 상관계수: 목표 > 0.85
    - 30개 팀 runs_scored RMSE: 목표 < 0.50 (경기당 득점 기준)
    - 30개 팀 runs_allowed 상관계수: 목표 > 0.80
```

### 4.2 득점 분포 비교

시뮬레이션의 득점 분포가 실제 분포와 유사한지.

```
방법:
  전체 시뮬레이션 경기의 팀별 이닝당 득점 분포 vs 실제 MLB 이닝당 득점 분포
  
  비교 항목:
  - 0점 이닝 비율: 실제 ≈ 73%, 시뮬레이션 허용 범위 70~76%
  - 1점 이닝 비율: 실제 ≈ 15%, 시뮬레이션 허용 범위 13~17%
  - 4+ 점 빅이닝 비율: 실제 ≈ 3%, 시뮬레이션 허용 범위 2~5%
  - 셧아웃 비율: 실제 ≈ 7%, 시뮬레이션 허용 범위 5~12%
  
  통계 검정:
  - KS test (Kolmogorov-Smirnov) 또는 Chi-square로 분포 비교
  - p-value > 0.05면 "분포가 유의하게 다르지 않다"
```

### 4.3 알려진 편향 추적

V0.1의 구조적 한계에서 오는 예상 편향을 명시적으로 측정.

```
측정 항목:
  1. 총 득점 편향 (현재 +0.7 runs/game)
     → 원인 후보: 에러 미반영, 투수 피로 미반영, 불펜 자동 교체
     
  2. 연장전 비율 편향 (현재 +2.8%p)
     → 원인 후보: 높은 득점이 동점 확률도 높일 수 있음
     
  3. 셧아웃 편향 (현재 +2.7%p)
     → 원인 후보: 투수 고정 라인업의 영향
```

---

## 5. L3: 경기 예측 검증

### 5.1 개별 경기 승률 예측 vs 실제 결과

2024 시즌 실제 경기를 시뮬레이션하고, 예측 승률과 실제 승패를 비교.

```
방법:
  2024 시즌 전 경기 (약 2,430경기)에 대해:
    1. 어웨이팀 vs 홈팀 매치업 구성
       - 라인업: 해당 팀의 고정 라인업 (V0.1은 일일 라인업 미반영)
       - 선발 투수: 해당 팀 대표 선발 (V0.1은 일일 선발 미반영)
       - 구장: 홈팀 구장
    2. 1,000회 시뮬레이션 → 어웨이 승률 산출
    3. 실제 결과 (1=승, 0=패)와 비교
    
  V0.1 한계: 매일 다른 선발투수/라인업을 반영하지 않으므로,
  같은 팀 매치업은 같은 승률이 나옴. 이는 예측 정밀도를 낮추지만,
  팀 전력 차이 반영 능력은 측정 가능.
```

#### 메트릭

| 메트릭 | 산출 방법 | V0.1 목표 | 의미 |
|--------|----------|-----------|------|
| Brier Score | mean((pred_win_pct - actual_outcome)²) | < 0.250 | 예측 확률의 정확도 (0=완벽, 0.25=동전던지기) |
| Log Loss | -mean(y·log(p) + (1-y)·log(1-p)) | < 0.695 | 정보 이론적 예측 정확도 (ln(2)≈0.693=동전던지기) |
| AUC-ROC | ROC 곡선 아래 면적 | > 0.55 | 승패 분류 능력 (0.5=무작위) |
| 칼리브레이션 | 예측 60% 승리 팀의 실제 승률 ≈ 60% | 오차 < 5%p | 확률의 신뢰도 |

*참고: V0.1에서 AUC > 0.55는 낮아 보이지만, 야구는 본질적으로 분산이 크고
매일 선발투수가 다르므로 고정 라인업 모델로 0.60 이상은 어렵다.
Phase 1에서 일일 선발투수를 반영하면 0.60+ 목표.*

### 5.2 칼리브레이션 차트

```
방법:
  1. 모든 경기의 예측 승률을 버킷으로 분류
     [0.40-0.45, 0.45-0.50, 0.50-0.55, 0.55-0.60, 0.60-0.65, ...]
  2. 각 버킷의 실제 승률 계산
  3. 예측 승률 vs 실제 승률 산포도 → 대각선에 가까울수록 잘 칼리브레이션됨

출력: calibration_chart.png (시각화)
```

---

## 6. L4: 시즌 예측 검증

### 6.1 팀별 시즌 승수 예측

```
방법:
  2024 시즌 전체를 시뮬레이션하여 팀별 시즌 승수를 예측하고, 실제와 비교.
  
  간이 방법 (V0.1):
    각 팀 쌍 (30C2 = 435조합)에 대해 승률을 산출하고,
    실제 일정의 상대 팀 빈도를 가중하여 시즌 승수 추정.
    
    team_win_pct = Σ(matchup_win_pct × games_vs_opponent) / 162
    predicted_wins = round(team_win_pct × 162)
  
  정밀 방법 (향후):
    실제 2024 일정의 모든 경기를 시뮬레이션 (선발투수 반영 시).

메트릭:
  - 30개 팀 승수 RMSE: 목표 < 8.0 (승 기준)
  - 30개 팀 승수 상관계수: 목표 > 0.75
  - 플레이오프 진출팀 적중률: 12팀 중 목표 ≥ 8팀
```

### 6.2 피타고라스 승률과의 비교

엔진의 예측력을 피타고라스 승률(Pythagorean expectation)과 비교하여 벤치마크.

```
피타고라스 승률:
  win_pct = RS^exp / (RS^exp + RA^exp)
  exp = 1.83 (Baseball Prospectus Pythagenpat 근사)

비교:
  만약 엔진 예측 승수 RMSE > 피타고라스 승수 RMSE라면,
  엔진의 득점 예측이 좋아도 경기 결과 변환에서 손실이 있다는 의미.
  
  만약 엔진 RMSE < 피타고라스 RMSE라면,
  엔진이 경기별 시뮬레이션을 통해 추가 정보를 잡아내고 있다는 의미.
```

---

## 7. 진단 도구

### 7.1 편향 분석 (Bias Analysis)

```python
def bias_analysis(predictions: list[float], actuals: list[float]) -> dict:
    """
    예측값과 실제값의 체계적 편향을 분석.
    
    Returns:
        {
            "mean_bias": float,           # 평균 편향 (양수=과대예측)
            "median_bias": float,
            "bias_by_quartile": dict,     # 상위/하위 선수 그룹별 편향
            "bias_by_hand": dict,         # 좌/우타 그룹별 편향
            "bias_direction": str,        # "overestimates" | "underestimates" | "balanced"
        }
    """
```

### 7.2 잔차 분석 (Residual Analysis)

```python
def residual_analysis(predictions: list[float], actuals: list[float]) -> dict:
    """
    예측 잔차의 패턴을 분석하여 모델의 체계적 약점을 발견.
    
    Returns:
        {
            "residual_distribution": dict,  # 잔차 분포 (정규분포에 가까워야 함)
            "residual_vs_predicted": float,  # 예측값과 잔차의 상관 (0에 가까워야 함)
            "outliers": list,               # 예측이 크게 빗나간 선수 목록
            "heteroscedasticity": float,    # 등분산성 검정 (Breusch-Pagan)
        }
    """
```

### 7.3 시뮬레이션 수렴 검증

```python
def convergence_check(
    away_team: Team, home_team: Team, park: ParkFactors, league: LeagueStats,
    n_trials: list[int] = [100, 500, 1000, 5000, 10000]
) -> dict:
    """
    Monte Carlo 시뮬레이션 횟수에 따른 결과 수렴 확인.
    
    Returns:
        {
            100:   {"win_pct": 0.542, "std": 0.050},
            500:   {"win_pct": 0.528, "std": 0.022},
            1000:  {"win_pct": 0.531, "std": 0.016},
            5000:  {"win_pct": 0.533, "std": 0.007},
            10000: {"win_pct": 0.532, "std": 0.005},
        }
    
    V0.1 기준: 1,000회에서 ±2%p 이내 수렴이면 충분.
    """
```

---

## 8. 보고서 생성

### 8.1 검증 보고서 (자동 생성)

```python
def generate_validation_report(
    data: DugoutData,
    actual: ActualResults,
    output_dir: str = "reports/"
) -> ValidationReport:
    """
    전체 검증을 실행하고 보고서를 생성.
    
    생성 파일:
      reports/
      ├── validation_summary.md          # 전체 요약
      ├── l1_player_accuracy.md          # L1 개별 선수 검증
      ├── l2_team_scoring.md             # L2 팀 득점 검증
      ├── l3_game_predictions.md         # L3 경기 예측 검증
      ├── l4_season_predictions.md       # L4 시즌 예측 검증
      ├── charts/
      │   ├── woba_predicted_vs_actual.png
      │   ├── team_runs_predicted_vs_actual.png
      │   ├── calibration_chart.png
      │   ├── residual_distribution.png
      │   ├── season_wins_predicted_vs_actual.png
      │   └── convergence_chart.png
      └── data/
          ├── player_predictions.csv     # 전체 선수 예측 vs 실제
          ├── team_predictions.csv       # 팀별 예측 vs 실제
          └── game_predictions.csv       # 경기별 예측 vs 실제
    """
```

### 8.2 요약 대시보드

```
╔══════════════════════════════════════════════════════╗
║           Dugout V0.1 Validation Report              ║
║                  2024 Season                         ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  L1: Player Accuracy                                 ║
║  ├─ wOBA RMSE:      0.028  (target: <0.030)  ✅     ║
║  ├─ wOBA corr:      0.83   (target: >0.80)   ✅     ║
║  ├─ K% RMSE:        0.035  (target: <0.040)  ✅     ║
║  ├─ BB% RMSE:       0.027  (target: <0.030)  ✅     ║
║  └─ HR/PA RMSE:     0.012  (target: <0.015)  ✅     ║
║                                                      ║
║  L2: Team Scoring                                    ║
║  ├─ Runs corr:      0.87   (target: >0.85)   ✅     ║
║  ├─ Runs RMSE:      0.42   (target: <0.50)   ✅     ║
║  └─ Scoring bias:   +0.7 R/G                 ⚠️     ║
║                                                      ║
║  L3: Game Predictions                                ║
║  ├─ Brier Score:    0.247  (target: <0.250)   ✅     ║
║  ├─ Log Loss:       0.690  (target: <0.695)   ✅     ║
║  └─ AUC-ROC:        0.56   (target: >0.55)   ✅     ║
║                                                      ║
║  L4: Season Predictions                              ║
║  ├─ Wins RMSE:      7.2    (target: <8.0)     ✅     ║
║  ├─ Wins corr:      0.78   (target: >0.75)    ✅     ║
║  └─ Playoff teams:  9/12   (target: ≥8)       ✅     ║
║                                                      ║
║  Pipeline Accuracy                                   ║
║  ├─ Spot check pass: 18/20                    ⚠️     ║
║  └─ Known issues: Judge BB%, HR/BIP gap       🔍     ║
║                                                      ║
╚══════════════════════════════════════════════════════╝

✅ = 목표 달성   ⚠️ = 주의 필요   ❌ = 목표 미달   🔍 = 조사 필요
```

*위 숫자는 예시. 실제 측정값은 구현 후 확인.*

---

## 9. 개선 추적 (Improvement Tracking)

### 9.1 버전별 메트릭 기록

```python
# metrics_history.json
{
    "v0.1.0": {
        "date": "2026-03-12",
        "changes": "Initial model — Log5, 2-stage, no splits",
        "l1_woba_rmse": 0.032,
        "l1_woba_corr": 0.81,
        "l2_runs_corr": 0.85,
        "l3_brier": 0.248,
        "l4_wins_rmse": 7.5
    },
    "v0.1.1": {
        "date": "...",
        "changes": "Added platoon splits",
        "l1_woba_rmse": 0.028,
        ...
    }
}
```

### 9.2 A/B 비교

```python
def compare_versions(metrics_a: dict, metrics_b: dict) -> dict:
    """
    두 버전의 메트릭을 비교하여 개선/악화를 판단.
    
    Returns:
        {
            "l1_woba_rmse": {"a": 0.032, "b": 0.028, "delta": -0.004, "improved": True},
            ...
        }
    """
```

---

## 10. 실행 인터페이스

### CLI

```bash
# 전체 검증 실행
python -m dugout.validation.run --season 2024

# 특정 레벨만
python -m dugout.validation.run --season 2024 --level L1

# 보고서 생성
python -m dugout.validation.run --season 2024 --report

# 두 버전 비교
python -m dugout.validation.compare --v1 v0.1.0 --v2 v0.1.1
```

### Python API

```python
from dugout.validation import ValidationRunner

runner = ValidationRunner(season=2024)

# 전체 검증
report = runner.run_all()
print(report.summary())

# L1만
l1 = runner.run_l1()
print(f"wOBA RMSE: {l1.woba_rmse:.3f}")

# 보고서 저장
report.save("reports/")
```

---

## 11. V0.1 명시적 제외 사항

| 제외 항목 | 이유 | 예정 Phase |
|----------|------|-----------|
| 일일 선발투수 반영 경기 예측 | 일일 라인업/선발 데이터 필요 | 1+ |
| 시즌 내 성적 변화 추적 | 월별/분기별 모델 업데이트 필요 | 2 |
| 실시간 예측 정확도 추적 | 일일 예측 서비스와 연동 | 3 |
| 다른 예측 모델과의 비교 | FiveThirtyEight, FanGraphs 등 | 2 |
| 배팅 라인 비교 (closing line) | 스포츠베팅 시장 데이터 필요 | 3 |

---

## 12. 구현 노트 (Claude Code용)

### 디렉토리 구조

```
dugout/
├── engine/                        # Phase 0-B, 0-CD (완료)
├── data/                          # Phase 0-A (완료)
├── validation/
│   ├── __init__.py
│   ├── runner.py                  # ValidationRunner 메인 클래스
│   ├── ground_truth.py            # ActualResults 로드/관리
│   ├── l1_player.py               # L1 개별 선수 검증
│   ├── l2_team.py                 # L2 팀 득점 검증
│   ├── l3_game.py                 # L3 경기 예측 검증
│   ├── l4_season.py               # L4 시즌 예측 검증
│   ├── diagnostics.py             # 편향/잔차/수렴 분석
│   ├── report.py                  # 보고서 생성
│   ├── charts.py                  # 시각화 (matplotlib)
│   └── compare.py                 # 버전 비교
├── reports/                       # 생성된 보고서 (gitignore)
├── tests/
│   ├── test_validation_l1.py
│   ├── test_validation_l2.py
│   ├── test_validation_l3.py
│   └── test_validation_l4.py
└── metrics_history.json           # 버전별 메트릭 기록
```

### 핵심 원칙

1. **검증은 엔진과 독립적.** validation 모듈은 엔진의 출력(확률 분포, 시뮬레이션 결과)만 소비. 엔진 내부를 참조하지 않음.

2. **재현 가능성.** 모든 시뮬레이션에 시드를 고정하여 동일 검증을 재현 가능하게.

3. **점진적 실행.** L1 → L2 → L3 → L4 순서로 실행 가능하되, 각 레벨은 독립적으로도 실행 가능.

4. **시각화 필수.** 숫자만으로는 패턴을 놓치기 쉬움. 산포도, 잔차 플롯, 칼리브레이션 차트는 필수 출력.

5. **L3/L4 실행 시간.** 2,430경기 × 1,000회 시뮬레이션은 시간이 오래 걸릴 수 있음.
   - 시뮬레이션 횟수를 조절 가능하게 (기본 1,000, 빠른 검증 시 100)
   - L3는 전체 2,430경기 대신 샘플 (예: 500경기)로 빠른 검증 가능하게

6. **경기별 예측(L3) 데이터 수집.**
   - 2024 전 경기 일정 + 결과가 필요
   - pybaseball의 `schedule_and_record` 또는 MLB Stats API에서 추출
   - 이 데이터는 ground_truth.py에서 관리

---

## 부록 A: 2024 시즌 주요 참고값

```
리그 평균:
  K%:     22.4%
  BB%:    8.5%
  HR/PA:  3.2%
  BABIP:  .296
  R/G:    4.30 (팀당)
  ERA:    4.08

팀 성적 범위 (2024):
  최다승: LAD 98승
  최소승: CHW 41승
  최다 득점: LAD ~5.2 R/G
  최소 득점: CHW ~3.2 R/G
  
연장전: 약 8%
셧아웃: 약 7%
```

---

## 부록 B: 메트릭 해석 가이드

### Brier Score

```
0.000 = 완벽한 예측 (모든 경기를 100% 확신하고 전부 맞힘)
0.250 = 동전 던지기 (모든 경기를 50%로 예측)
0.333 = 나쁜 예측 (체계적으로 틀림)

야구 맥락:
  - 최고의 모델도 0.230 이하는 어려움 (야구의 본질적 불확실성)
  - 0.240~0.250이면 "팀 전력 차이를 반영하고 있다"
  - 0.250 이상이면 "동전 던지기보다 나을 게 없다"
```

### wOBA RMSE

```
0.000 = 모든 선수의 wOBA를 정확히 예측
0.030 = 평균 30포인트 오차 (.320 선수를 .290~.350 범위로 예측)
0.050 = 평균 50포인트 오차 (실용적 가치 낮음)

맥락:
  - wOBA의 표준편차가 약 .060이므로, RMSE 0.030은 분산의 절반을 설명
  - Marcel projection의 wOBA RMSE가 약 0.030~0.035
  - 0.030 이하면 V0.1으로서 Marcel 수준이므로 충분
```
