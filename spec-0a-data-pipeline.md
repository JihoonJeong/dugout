# Dugout — Phase 0-A: 데이터 파이프라인 스펙

> **Version:** 0.1.0
> **Status:** Draft
> **Author:** JJ + Luca
> **Date:** 2026-03-12
> **소비자:** Phase 0-B (타석 확률 모델), Phase 0-CD (게임 시뮬레이션)

---

## 1. 목적

pybaseball 및 MLB 공개 데이터에서 선수/팀/리그 통계를 추출하여,
Dugout 시뮬레이션 엔진이 소비하는 데이터 클래스(`BatterStats`, `PitcherStats`, `LeagueStats`, `ParkFactors`, `Team`)로 변환하는 파이프라인.

### 설계 원칙

1. **단일 시즌(2024)으로 시작**, 함수 시그니처에 `season: int` 파라미터를 두어 다년도 확장 가능
2. **Raw → Intermediate → Engine-ready** 3단계 변환
3. **캐싱:** pybaseball API 호출은 느리므로, raw 데이터를 로컬 CSV/Parquet로 캐싱
4. **검증:** 변환 후 데이터 무결성 체크 (누락, 범위 이탈, 합계 불일치)

---

## 2. 데이터 소스 & 추출

### 2.1 pybaseball 주요 함수

| 데이터 | pybaseball 함수 | 설명 |
|--------|-----------------|------|
| 타자 시즌 성적 | `batting_stats(season)` | FanGraphs 기반 시즌 통계 |
| 투수 시즌 성적 | `pitching_stats(season)` | FanGraphs 기반 시즌 통계 |
| 타자 분할 성적 | `batting_stats(season, split_seasons=False, qual=0)` + FanGraphs splits | vs LHP/RHP |
| 투수 분할 성적 | `pitching_stats(season, split_seasons=False, qual=0)` + FanGraphs splits | vs LHB/RHB |
| Park factors | FanGraphs Guts! 또는 `team_batting(season)` | 구장별 보정 계수 |
| 팀 로스터 | MLB Stats API (`statsapi`) | 40인 로스터, 포지션, 투타 |
| 선수 ID 매핑 | `playerid_lookup()`, `playerid_reverse_lookup()` | FanGraphs ID ↔ MLB ID 매핑 |

### 2.2 FanGraphs splits 접근

pybaseball의 `batting_stats`는 전체 성적만 반환. 좌우 분할은 별도 처리 필요.

```python
# 방법 1: pybaseball의 FanGraphs 스크래핑
from pybaseball import batting_stats

# qual=0 → 최소 PA 제한 없이 전원 추출
all_batters = batting_stats(2024, qual=0)

# 방법 2: FanGraphs splits 페이지 직접 접근
# pybaseball이 splits를 직접 지원하지 않으면, 
# FanGraphs 리더보드 URL에 split 파라미터를 추가하여 스크래핑
# (구체적 방법은 구현 시 pybaseball 최신 API 확인)

# 방법 3: Statcast 데이터에서 직접 계산
from pybaseball import statcast
# pitcher_hand 컬럼으로 vs LHP/RHP 분할 가능
```

**구현 시 결정:** pybaseball의 splits 지원 여부를 먼저 확인.
지원하면 사용, 지원하지 않으면 Statcast play-by-play에서 직접 집계.

### 2.3 추출 범위

```
V0.1 기준: 2024 시즌
  - 타자: PA ≥ 1인 모든 타자 (약 900명)
  - 투수: IP ≥ 1인 모든 투수 (약 700명)
  - 팀: 30개 MLB 팀
  - 구장: 30개 MLB 구장

향후 확장:
  - season 파라미터로 2022, 2023 등 추가 가능
  - 다년도 가중평균 (Marcel) 로직은 별도 모듈
```

---

## 3. 변환 파이프라인

### 3.1 Raw → Intermediate

pybaseball의 DataFrame을 정규화된 중간 형태로 변환.

#### 타자 Intermediate

```python
@dataclass
class BatterIntermediate:
    player_id: str          # FanGraphs ID (문자열)
    mlb_id: Optional[str]   # MLB Stats API ID
    name: str
    team: str
    hand: str               # "L", "R", "S"
    season: int
    
    # 전체 성적 (raw counts)
    pa: int
    ab: int
    hits: int               # H
    singles: int            # 1B
    doubles: int            # 2B
    triples: int            # 3B
    home_runs: int          # HR
    walks: int              # BB (비고의)
    strikeouts: int         # K (SO)
    hbp: int                # HBP
    
    # 타구 유형 (raw counts)
    ground_balls: int       # GB
    fly_balls: int          # FB
    line_drives: int        # LD
    
    # 분할 성적 (Optional)
    vs_lhp: Optional[dict]  # {"pa": int, "k": int, "bb": int, ...}
    vs_rhp: Optional[dict]
```

**핵심 변환 로직:**

```
BIP (Balls In Play) 산출:
  bip = pa - strikeouts - walks - hbp
  
  검증: bip ≈ ab - strikeouts - home_runs + sacrifice_flies + sacrifice_hits
  (정확히 일치하지 않을 수 있음 — 희생번트 등 때문. 근사값으로 허용)

GO/FO 산출:
  pybaseball의 GB/FB 카운트를 사용.
  GB → GO로, FB → FO로 매핑.
  
  주의: pybaseball의 GB에는 내야안타도 포함될 수 있음.
  정확한 GO = GB - IFFB가 아닌 히트 제외 필요.
  
  V0.1 근사:
    total_outs_bip = bip - singles - doubles - triples - home_runs
    go_count = ground_balls 중 아웃 = round(total_outs_bip × (ground_balls / (ground_balls + fly_balls + line_drives)))
    fo_count = total_outs_bip - go_count
    
  이 근사는 라인드라이브 아웃을 FO에 흡수하는 V0.1 결정과 일관됨.
```

#### 투수 Intermediate

```python
@dataclass
class PitcherIntermediate:
    player_id: str
    mlb_id: Optional[str]
    name: str
    team: str
    hand: str               # "L", "R"
    season: int
    role: str               # "SP" (선발) | "RP" (불펜)
    
    # 전체 성적 (raw counts)
    pa_against: int         # TBF (Batters Faced)
    ip: float               # Innings Pitched
    hits_allowed: int
    home_runs_allowed: int
    walks_allowed: int      # BB
    strikeouts: int         # K (SO)
    hbp: int
    
    # 타구 유형 허용
    ground_balls: int       # GB
    fly_balls: int          # FB
    
    # 분할 성적 (Optional)
    vs_lhb: Optional[dict]
    vs_rhb: Optional[dict]
```

### 3.2 Intermediate → Engine-ready

중간 형태에서 0-B/0-CD가 요구하는 데이터 클래스로 변환.

#### BatterIntermediate → BatterStats

```python
def to_batter_stats(bi: BatterIntermediate, league: LeagueStats) -> BatterStats:
    
    # Rate 계산
    k_rate = bi.strikeouts / bi.pa
    bb_rate = bi.walks / bi.pa
    hbp_rate = bi.hbp / bi.pa
    
    bip = bi.pa - bi.strikeouts - bi.walks - bi.hbp
    
    # BIP 내 결과 비율
    if bip > 0:
        single_rate_bip = bi.singles / bip
        double_rate_bip = bi.doubles / bip
        triple_rate_bip = bi.triples / bip
        hr_rate_bip = bi.home_runs / bip
        
        # GO/FO 산출
        outs_bip = bip - bi.singles - bi.doubles - bi.triples - bi.home_runs
        total_batted = bi.ground_balls + bi.fly_balls + bi.line_drives
        
        if total_batted > 0 and outs_bip > 0:
            gb_share = bi.ground_balls / total_batted
            go_count = round(outs_bip * gb_share)
            fo_count = outs_bip - go_count
            
            go_rate_bip = go_count / bip
            fo_rate_bip = fo_count / bip
        else:
            # 타구 데이터 없으면 리그 평균
            go_rate_bip = league.go_rate_bip
            fo_rate_bip = league.fo_rate_bip
    else:
        # BIP 없음 (PA 극소) → 리그 평균
        single_rate_bip = league.single_rate_bip
        # ... (전부 리그 평균)
    
    # BIP 내 비율 합 = 1.0 정규화
    bip_total = single_rate_bip + double_rate_bip + triple_rate_bip + hr_rate_bip + go_rate_bip + fo_rate_bip
    if abs(bip_total - 1.0) > 0.01:
        # 정규화
        single_rate_bip /= bip_total
        double_rate_bip /= bip_total
        triple_rate_bip /= bip_total
        hr_rate_bip /= bip_total
        go_rate_bip /= bip_total
        fo_rate_bip /= bip_total
    
    # Platoon splits 변환
    splits = None
    if bi.vs_lhp is not None and bi.vs_rhp is not None:
        splits = {
            "vs_LHP": convert_split_rates(bi.vs_lhp, bip_fallback=...),
            "vs_RHP": convert_split_rates(bi.vs_rhp, bip_fallback=...),
        }
    
    # 소표본 floor 처리
    k_rate = max(k_rate, 0.001)
    bb_rate = max(bb_rate, 0.001)
    hbp_rate = max(hbp_rate, 0.001)
    
    return BatterStats(
        player_id=bi.player_id,
        name=bi.name,
        hand=bi.hand,
        pa=bi.pa,
        k_rate=k_rate,
        bb_rate=bb_rate,
        hbp_rate=hbp_rate,
        single_rate_bip=single_rate_bip,
        double_rate_bip=double_rate_bip,
        triple_rate_bip=triple_rate_bip,
        hr_rate_bip=hr_rate_bip,
        go_rate_bip=go_rate_bip,
        fo_rate_bip=fo_rate_bip,
        splits=splits
    )
```

#### PitcherIntermediate → PitcherStats

```python
def to_pitcher_stats(pi: PitcherIntermediate, league: LeagueStats) -> PitcherStats:
    
    k_rate = pi.strikeouts / pi.pa_against
    bb_rate = pi.walks_allowed / pi.pa_against
    hbp_rate = pi.hbp / pi.pa_against
    
    bip = pi.pa_against - pi.strikeouts - pi.walks_allowed - pi.hbp
    
    hr_rate_bip = pi.home_runs_allowed / bip if bip > 0 else league.hr_rate_bip
    
    # GO/FO ratio
    if pi.fly_balls > 0:
        go_fo_ratio = pi.ground_balls / pi.fly_balls
    else:
        go_fo_ratio = league.go_fo_ratio
    
    # Floor 처리
    k_rate = max(k_rate, 0.001)
    bb_rate = max(bb_rate, 0.001)
    hbp_rate = max(hbp_rate, 0.001)
    hr_rate_bip = max(hr_rate_bip, 0.001)
    go_fo_ratio = max(go_fo_ratio, 0.1)  # 극단적 플라이볼 투수라도 0.1 이상
    
    # Splits
    splits = None
    if pi.vs_lhb is not None and pi.vs_rhb is not None:
        splits = {
            "vs_LHB": convert_pitcher_split_rates(pi.vs_lhb),
            "vs_RHB": convert_pitcher_split_rates(pi.vs_rhb),
        }
    
    return PitcherStats(
        player_id=pi.player_id,
        name=pi.name,
        hand=pi.hand,
        pa_against=pi.pa_against,
        k_rate=k_rate,
        bb_rate=bb_rate,
        hbp_rate=hbp_rate,
        hr_rate_bip=hr_rate_bip,
        go_fo_ratio=go_fo_ratio,
        splits=splits
    )
```

### 3.3 리그 평균 산출

```python
def calculate_league_stats(
    all_batters: list[BatterIntermediate],
    season: int
) -> LeagueStats:
    """
    전체 타자 데이터를 합산하여 리그 평균 rate 산출.
    PA 기반 가중평균이 아닌, 리그 전체 합산 (raw counts 합산 후 rate 계산).
    """
    
    total_pa = sum(b.pa for b in all_batters)
    total_k = sum(b.strikeouts for b in all_batters)
    total_bb = sum(b.walks for b in all_batters)
    total_hbp = sum(b.hbp for b in all_batters)
    total_1b = sum(b.singles for b in all_batters)
    total_2b = sum(b.doubles for b in all_batters)
    total_3b = sum(b.triples for b in all_batters)
    total_hr = sum(b.home_runs for b in all_batters)
    total_gb = sum(b.ground_balls for b in all_batters)
    total_fb = sum(b.fly_balls for b in all_batters)
    total_ld = sum(b.line_drives for b in all_batters)
    
    total_bip = total_pa - total_k - total_bb - total_hbp
    total_outs_bip = total_bip - total_1b - total_2b - total_3b - total_hr
    total_batted = total_gb + total_fb + total_ld
    
    gb_share = total_gb / total_batted if total_batted > 0 else 0.45
    go_count = round(total_outs_bip * gb_share)
    fo_count = total_outs_bip - go_count
    
    return LeagueStats(
        season=season,
        k_rate=total_k / total_pa,
        bb_rate=total_bb / total_pa,
        hbp_rate=total_hbp / total_pa,
        single_rate_bip=total_1b / total_bip,
        double_rate_bip=total_2b / total_bip,
        triple_rate_bip=total_3b / total_bip,
        hr_rate_bip=total_hr / total_bip,
        go_rate_bip=go_count / total_bip,
        fo_rate_bip=fo_count / total_bip,
        go_fo_ratio=total_gb / total_fb if total_fb > 0 else 1.0
    )
```

### 3.4 Park Factor 추출

```python
def extract_park_factors(season: int) -> dict[str, ParkFactors]:
    """
    FanGraphs의 구장별 park factor 추출.
    
    Returns:
        {"Yankee Stadium": ParkFactors(...), "Dodger Stadium": ParkFactors(...), ...}
    """
    
    # 방법 1: pybaseball의 팀 통계에서 park factor 추출
    # FanGraphs 팀 페이지에 park factor 포함
    
    # 방법 2: FanGraphs Guts! 페이지 스크래핑
    # https://www.fangraphs.com/guts.aspx?type=pf&season=2024
    
    # 방법 3: 수동 하드코딩 (30개 구장이므로 관리 가능)
    # → V0.1 fallback
    
    # 구현 시 방법 1 또는 2 시도, 실패 시 방법 3
    
    # 반환 형태
    return {
        park_name: ParkFactors(
            park_name=park_name,
            pf_1b=pf_data["1B"],   # 100 = neutral
            pf_2b=pf_data["2B"],
            pf_3b=pf_data["3B"],
            pf_hr=pf_data["HR"]
        )
        for park_name, pf_data in raw_park_factors.items()
    }
```

### 3.5 팀 구성 (Team)

```python
def build_team(
    team_id: str,
    season: int,
    all_batters: dict[str, BatterStats],      # player_id → BatterStats
    all_pitchers: dict[str, PitcherStats],     # player_id → PitcherStats
    roster_data: dict                           # MLB API 로스터 정보
) -> Team:
    """
    MLB API 로스터 데이터를 기반으로 팀 구성.
    
    선발 라인업: 해당 팀 소속 타자 중 PA 상위 9명 (포지션 무관, V0.1 단순화)
    선발 투수: 해당 팀 SP 중 IP 최다
    불펜: 해당 팀 RP 중 IP 상위 5명 (사용 순서: IP 순)
    """
    
    team_batters = [b for b in all_batters.values() if b.team == team_id]
    team_pitchers = [p for p in all_pitchers.values() if p.team == team_id]
    
    # 라인업: PA 상위 9명
    lineup = sorted(team_batters, key=lambda b: b.pa, reverse=True)[:9]
    
    # 타순 배치 (V0.1: PA 순서 그대로. Phase 1에서 최적 타순 알고리즘)
    # 실제로는 감독이 타순을 결정하지만, V0.1에서는 자동 배치
    
    # 선발 투수
    starters = [p for p in team_pitchers if p.role == "SP"]
    starter = max(starters, key=lambda p: p.innings_pitched) if starters else team_pitchers[0]
    
    # 불펜
    relievers = [p for p in team_pitchers if p.role == "RP"]
    bullpen = sorted(relievers, key=lambda p: p.innings_pitched, reverse=True)[:5]
    
    return Team(
        team_id=team_id,
        name=TEAM_NAMES[team_id],
        lineup=lineup,
        starter=starter,
        bullpen=bullpen
    )
```

---

## 4. 팀/구장 매핑

### 팀 ID → 팀명 → 구장명

```python
TEAM_MAPPING = {
    "ARI": {"name": "Arizona Diamondbacks",     "park": "Chase Field"},
    "ATL": {"name": "Atlanta Braves",           "park": "Truist Park"},
    "BAL": {"name": "Baltimore Orioles",        "park": "Oriole Park at Camden Yards"},
    "BOS": {"name": "Boston Red Sox",           "park": "Fenway Park"},
    "CHC": {"name": "Chicago Cubs",             "park": "Wrigley Field"},
    "CHW": {"name": "Chicago White Sox",        "park": "Guaranteed Rate Field"},
    "CIN": {"name": "Cincinnati Reds",          "park": "Great American Ball Park"},
    "CLE": {"name": "Cleveland Guardians",      "park": "Progressive Field"},
    "COL": {"name": "Colorado Rockies",         "park": "Coors Field"},
    "DET": {"name": "Detroit Tigers",           "park": "Comerica Park"},
    "HOU": {"name": "Houston Astros",           "park": "Minute Maid Park"},
    "KCR": {"name": "Kansas City Royals",       "park": "Kauffman Stadium"},
    "LAA": {"name": "Los Angeles Angels",       "park": "Angel Stadium"},
    "LAD": {"name": "Los Angeles Dodgers",      "park": "Dodger Stadium"},
    "MIA": {"name": "Miami Marlins",            "park": "loanDepot Park"},
    "MIL": {"name": "Milwaukee Brewers",        "park": "American Family Field"},
    "MIN": {"name": "Minnesota Twins",          "park": "Target Field"},
    "NYM": {"name": "New York Mets",            "park": "Citi Field"},
    "NYY": {"name": "New York Yankees",         "park": "Yankee Stadium"},
    "OAK": {"name": "Oakland Athletics",        "park": "Oakland Coliseum"},
    "PHI": {"name": "Philadelphia Phillies",    "park": "Citizens Bank Park"},
    "PIT": {"name": "Pittsburgh Pirates",       "park": "PNC Park"},
    "SDP": {"name": "San Diego Padres",         "park": "Petco Park"},
    "SFG": {"name": "San Francisco Giants",     "park": "Oracle Park"},
    "SEA": {"name": "Seattle Mariners",         "park": "T-Mobile Park"},
    "STL": {"name": "St. Louis Cardinals",      "park": "Busch Stadium"},
    "TBR": {"name": "Tampa Bay Rays",           "park": "Tropicana Field"},
    "TEX": {"name": "Texas Rangers",            "park": "Globe Life Field"},
    "TOR": {"name": "Toronto Blue Jays",        "park": "Rogers Centre"},
    "WSN": {"name": "Washington Nationals",     "park": "Nationals Park"},
}
```

*참고: OAK는 2024 시즌 기준. 2025+에서 새크라멘토로 이전.*

---

## 5. pybaseball 컬럼 매핑

pybaseball이 반환하는 DataFrame의 컬럼명은 FanGraphs 기반이며, 때때로 변경됨.
아래 매핑은 2024 기준이며, **구현 시 실제 컬럼명을 확인하고 업데이트해야 함.**

### 타자 (`batting_stats`)

| 엔진 필드 | pybaseball 컬럼 | 비고 |
|-----------|-----------------|------|
| name | `Name` | |
| team | `Team` | 약칭 (NYY, LAD 등) |
| pa | `PA` | |
| ab | `AB` | |
| hits | `H` | |
| singles | `1B` | pybaseball이 직접 제공하지 않으면: H - 2B - 3B - HR |
| doubles | `2B` | |
| triples | `3B` | |
| home_runs | `HR` | |
| walks | `BB` | IBB 포함 여부 확인 필요. 가능하면 비고의만 |
| strikeouts | `SO` | |
| hbp | `HBP` | |
| ground_balls | `GB` | FanGraphs batted ball 데이터. 비율(%)로 제공 시 AB-K로 역산 |
| fly_balls | `FB` | 동일 |
| line_drives | `LD` | 동일 |
| hand | — | pybaseball에 없을 수 있음. MLB API 또는 별도 소스 필요 |
| player_id | `IDfg` | FanGraphs ID |

### 투수 (`pitching_stats`)

| 엔진 필드 | pybaseball 컬럼 | 비고 |
|-----------|-----------------|------|
| name | `Name` | |
| team | `Team` | |
| pa_against | `TBF` | Total Batters Faced |
| ip | `IP` | |
| hits_allowed | `H` | |
| home_runs_allowed | `HR` | |
| walks_allowed | `BB` | |
| strikeouts | `SO` | |
| hbp | `HBP` | |
| ground_balls | `GB` | 비율(%)일 수 있음 |
| fly_balls | `FB` | 비율(%)일 수 있음 |
| hand | — | 별도 소스 필요 |
| role | — | GS (Games Started) > 0이면 SP, 아니면 RP로 근사 |
| player_id | `IDfg` | |

### GB/FB가 비율(%)로 제공되는 경우

```python
# FanGraphs는 GB%, FB%, LD%를 제공 (합 = 100%)
# raw count 역산:
#   total_batted_balls = AB - SO  (근사)
#   ground_balls = round(total_batted_balls * gb_pct / 100)
#   fly_balls = round(total_batted_balls * fb_pct / 100)
#   line_drives = total_batted_balls - ground_balls - fly_balls
```

---

## 6. 타자 투타 (Hand) 데이터

pybaseball의 `batting_stats`에 투타 정보가 없을 수 있음. 별도 소스 필요.

### 접근 방법 (우선순위)

```
1. pybaseball의 playerid 관련 함수에서 추출
   - playerid_lookup(last, first) → 'bats' 컬럼

2. MLB Stats API
   - statsapi.get('person', {'personId': mlb_id}) → people[0]['batSide']['code']
   - 'R', 'L', 'S' (Switch)

3. Lahman Database
   - People 테이블의 'bats' 컬럼

4. FanGraphs 선수 페이지 스크래핑 (최후 수단)
```

**V0.1 구현 전략:**
MLB Stats API로 30개 팀 로스터를 한 번에 가져오면 전 선수의 투타 정보를 얻을 수 있음.
이 데이터를 player_id 매핑 테이블에 저장하고, FanGraphs 데이터와 조인.

```python
def fetch_player_hands(season: int) -> dict[str, str]:
    """
    MLB API에서 전 선수의 투타 정보 추출.
    
    Returns:
        {"mlb_id": "R", "mlb_id": "L", ...}  # bats
        
    투수의 경우: throws 정보도 함께 추출
        {"mlb_id": {"bats": "R", "throws": "L"}, ...}
    """
    import statsapi
    
    hands = {}
    for team_id in range(108, 160):  # MLB team IDs 범위
        try:
            roster = statsapi.roster(team_id, season=season)
            # 파싱하여 hands에 추가
        except:
            continue
    
    return hands
```

---

## 7. 주자 진루 확률 테이블 업데이트

0-CD 스펙의 주자 진루 확률은 근사값이었음. 0-A에서 실제 데이터 기반으로 업데이트.

### 데이터 소스

```
Retrosheet play-by-play (2019-2023, 5시즌 합산)
또는 Baseball Savant의 Statcast 데이터

추출 방법:
  모든 싱글 이벤트에서:
    1루 주자가 있었던 경우 → 최종 위치 집계
    2루 주자가 있었던 경우 → 최종 위치 집계
    3루 주자가 있었던 경우 → 최종 위치 집계
  
  → 진루 확률 테이블 생성
```

### 구현

```python
def calculate_runner_advance_probabilities(
    seasons: list[int] = [2019, 2020, 2021, 2022, 2023]
) -> dict:
    """
    Retrosheet 또는 Statcast 데이터에서 주자 진루 확률 테이블 산출.
    
    Returns:
        {
            "1B": {  # 싱글 시
                "runner_1B": {"2B": 0.42, "3B": 0.48, "HOME": 0.10},
                "runner_2B": {"3B": 0.28, "HOME": 0.72},
                "runner_3B": {"HOME": 0.96, "3B": 0.04},
            },
            "2B": { ... },
            "GO": {
                "dp_rate": 0.53,
                "dp_runner_3B_scores": 0.48,
                ...
            },
            "FO": {
                "sf_rate": 0.63,
                ...
            }
        }
    """
    pass  # 구현 시 Retrosheet 파싱 또는 Statcast 집계
```

**V0.1 전략:** Retrosheet 파싱이 복잡하면, 0-CD 스펙의 근사값을 그대로 사용하고,
이 함수는 "데이터가 있으면 테이블을 업데이트하는" optional 모듈로 둔다.

---

## 8. 캐싱 전략

### 로컬 캐시 구조

```
dugout/
├── cache/
│   ├── raw/
│   │   ├── batting_stats_2024.parquet
│   │   ├── pitching_stats_2024.parquet
│   │   ├── player_hands_2024.json
│   │   └── park_factors_2024.json
│   ├── intermediate/
│   │   ├── batters_2024.parquet
│   │   └── pitchers_2024.parquet
│   └── engine/
│       ├── batter_stats_2024.pkl      # dict[str, BatterStats]
│       ├── pitcher_stats_2024.pkl     # dict[str, PitcherStats]
│       ├── league_stats_2024.pkl      # LeagueStats
│       ├── park_factors_2024.pkl      # dict[str, ParkFactors]
│       └── teams_2024.pkl             # dict[str, Team]
```

### 캐시 로직

```python
def load_or_fetch(cache_path: str, fetch_fn, force_refresh: bool = False):
    """
    캐시 파일이 있으면 로드, 없거나 force_refresh면 fetch_fn 실행 후 저장.
    """
    if not force_refresh and os.path.exists(cache_path):
        return load(cache_path)
    
    data = fetch_fn()
    save(data, cache_path)
    return data
```

**캐시 무효화:** `force_refresh=True`로 수동 갱신. 날짜 기반 자동 무효화는 V0.1에서 미구현.

---

## 9. 메인 파이프라인 인터페이스

```python
class DugoutDataPipeline:
    """Dugout 엔진에 데이터를 공급하는 메인 파이프라인."""
    
    def __init__(self, cache_dir: str = "cache/", season: int = 2024):
        self.cache_dir = cache_dir
        self.season = season
    
    def load_all(self, force_refresh: bool = False) -> DugoutData:
        """
        전체 데이터를 로드하여 엔진에 공급 가능한 형태로 반환.
        
        Returns:
            DugoutData with all_batters, all_pitchers, league, parks, teams
        """
        
        # 1. Raw 데이터 추출 (또는 캐시 로드)
        raw_batting = self._fetch_batting(force_refresh)
        raw_pitching = self._fetch_pitching(force_refresh)
        player_hands = self._fetch_player_hands(force_refresh)
        raw_park_factors = self._fetch_park_factors(force_refresh)
        
        # 2. Intermediate 변환
        batters_int = self._transform_batters(raw_batting, player_hands)
        pitchers_int = self._transform_pitchers(raw_pitching, player_hands)
        
        # 3. 리그 평균 산출
        league = calculate_league_stats(batters_int, self.season)
        
        # 4. Engine-ready 변환
        all_batters = {b.player_id: to_batter_stats(b, league) for b in batters_int}
        all_pitchers = {p.player_id: to_pitcher_stats(p, league) for p in pitchers_int}
        parks = extract_park_factors(self.season)
        
        # 5. 팀 구성
        teams = {}
        for team_id in TEAM_MAPPING:
            teams[team_id] = build_team(team_id, self.season, all_batters, all_pitchers, roster_data={})
        
        # 6. 검증
        self._validate(all_batters, all_pitchers, league, parks, teams)
        
        return DugoutData(
            season=self.season,
            all_batters=all_batters,
            all_pitchers=all_pitchers,
            league=league,
            parks=parks,
            teams=teams
        )


@dataclass
class DugoutData:
    season: int
    all_batters: dict[str, BatterStats]
    all_pitchers: dict[str, PitcherStats]
    league: LeagueStats
    parks: dict[str, ParkFactors]
    teams: dict[str, Team]
    
    def get_matchup(self, away_id: str, home_id: str) -> tuple[Team, Team, ParkFactors]:
        """경기 시뮬레이션을 위한 매치업 데이터 추출."""
        away = self.teams[away_id]
        home = self.teams[home_id]
        park = self.parks[TEAM_MAPPING[home_id]["park"]]
        return away, home, park
```

---

## 10. 데이터 검증

### 파이프라인 내 검증 (자동)

```
1. 선수 수 검증:
   - 타자 ≥ 500명 (2024 기준 약 900명)
   - 투수 ≥ 400명 (2024 기준 약 700명)
   - 각 팀 타자 ≥ 9명, 투수 ≥ 6명 (선발 1 + 불펜 5)

2. Rate 범위 검증 (개별 선수):
   - 0 < K% < 0.60
   - 0 < BB% < 0.30
   - 0 < HBP% < 0.10
   - BIP 내 비율 합 = 1.0 (±0.01)

3. 리그 평균 범위 검증:
   - K%: 0.18 ~ 0.28 (2024 MLB ≈ 0.224)
   - BB%: 0.06 ~ 0.12 (2024 MLB ≈ 0.085)
   - HR/BIP: 0.05 ~ 0.15 (2024 MLB ≈ 0.092)
   - BABIP 역산: 0.270 ~ 0.320 (2024 MLB ≈ 0.296)
     BABIP = (1B + 2B + 3B) / (BIP - HR)

4. Park Factor 범위:
   - 모든 이벤트: 70 ≤ pf ≤ 140
   - 쿠어스 필드 HR: > 110 (알려진 극단값 확인)

5. 팀 구성 검증:
   - 모든 30개 팀 존재
   - 각 팀 lineup 9명
   - 각 팀 starter 1명
   - 각 팀 bullpen ≥ 4명

6. ID 일관성:
   - 팀 lineup의 모든 player_id가 all_batters에 존재
   - 팀 starter/bullpen의 모든 player_id가 all_pitchers에 존재
```

### 수동 Sanity Check

```
7. 알려진 선수 스팟 체크:
   - Aaron Judge 2024: K% ≈ 0.223, BB% ≈ 0.150, HR ≈ 58
   - Shohei Ohtani 2024 (타자): HR ≈ 54, SB ≈ 59 (SB는 V0.1 미사용이지만 데이터 확인)
   - Gerrit Cole 2024: K% ≈ 0.264, BB% ≈ 0.058
   
   엔진 변환 후에도 이 수치가 보존되는지 확인.

8. 리그 평균 복원:
   - 전체 선수 가중평균(PA 가중) ≈ league stats 값 (±1%)
```

---

## 11. ID 매핑

pybaseball (FanGraphs ID)과 MLB API (MLB ID)는 다른 ID 체계를 사용.

```python
# pybaseball 제공 매핑
from pybaseball import playerid_lookup, playerid_reverse_lookup

# FanGraphs ID → MLB ID 매핑 테이블
# pybaseball의 chadwick register에서 추출 가능

def build_id_mapping(season: int) -> dict:
    """
    FanGraphs ID ↔ MLB ID 양방향 매핑 테이블 생성.
    
    Returns:
        {
            "fg_to_mlb": {"fg_12345": "mlb_67890", ...},
            "mlb_to_fg": {"mlb_67890": "fg_12345", ...}
        }
    """
    # pybaseball의 chadwick register 활용
    from pybaseball import chadwick_register
    reg = chadwick_register()
    # key_fangraphs, key_mlbam 컬럼으로 매핑
    pass
```

**V0.1 전략:** FanGraphs ID를 기본 ID로 사용. MLB API 호출 시만 매핑 테이블 참조.

---

## 12. V0.1 명시적 제외 사항

| 제외 항목 | 이유 | 예정 Phase |
|----------|------|-----------|
| 다년도 가중평균 (Marcel) | 단일 시즌으로 시작 | 1 |
| Statcast pitch-level 데이터 | 구종별 매치업은 Phase 2 | 2 |
| 실시간 데이터 갱신 | 일일 예측 서비스 시 필요 | 3 |
| 부상 정보 자동 수집 | IL 상태 반영 필요 | 3 |
| 마이너리그 선수 데이터 | 콜업 시뮬레이션 시 필요 | 2 |
| 연봉/계약 데이터 | 트레이드/FA 시뮬레이션 시 필요 | 2 |
| 날씨/기상 데이터 | 기상 보정 시 필요 | 3 |
| 심판 데이터 | 심판별 스트라이크존 보정 | 2+ |

---

## 13. 구현 노트 (Claude Code용)

### 디렉토리 구조

```
dugout/
├── engine/
│   ├── __init__.py
│   ├── at_bat.py              # Phase 0-B (완료)
│   ├── models.py              # 데이터 클래스 (확장)
│   ├── constants.py           # 매직 넘버
│   ├── game.py                # Phase 0-CD (완료)
│   ├── runners.py             # Phase 0-CD (완료)
│   ├── pitching.py            # Phase 0-CD (완료)
│   └── monte_carlo.py         # Phase 0-CD (완료)
├── data/
│   ├── __init__.py
│   ├── pipeline.py            # 이 스펙의 핵심: DugoutDataPipeline
│   ├── extract.py             # pybaseball API 호출 + raw 데이터 추출
│   ├── transform.py           # Raw → Intermediate → Engine-ready 변환
│   ├── park_factors.py        # Park factor 추출/관리
│   ├── team_builder.py        # 팀 구성 로직
│   ├── id_mapping.py          # FanGraphs ↔ MLB ID 매핑
│   ├── runner_tables.py       # 주자 진루 확률 (데이터 기반 업데이트)
│   └── constants.py           # TEAM_MAPPING 등
├── cache/                     # 캐시 디렉토리 (gitignore)
│   ├── raw/
│   ├── intermediate/
│   └── engine/
├── tests/
│   ├── test_at_bat.py         # Phase 0-B (완료)
│   ├── test_runners.py        # Phase 0-CD (완료)
│   ├── test_game.py           # Phase 0-CD (완료)
│   ├── test_pitching.py       # Phase 0-CD (완료)
│   ├── test_monte_carlo.py    # Phase 0-CD (완료)
│   ├── test_sanity.py         # Phase 0-CD (완료)
│   ├── test_pipeline.py       # 파이프라인 통합 테스트
│   ├── test_extract.py        # 데이터 추출 테스트
│   ├── test_transform.py      # 변환 로직 테스트
│   └── test_validation.py     # 데이터 검증 테스트
└── notebooks/
    └── explore.ipynb
```

### 핵심 원칙

1. **pybaseball 의존성 격리:** `extract.py`만 pybaseball을 직접 호출.
   나머지 모듈은 DataFrame 또는 Intermediate 객체를 받음.
   이렇게 해야 pybaseball API가 변경되더라도 `extract.py`만 수정하면 됨.

2. **실패에 강건한 파이프라인:** pybaseball 호출 실패 시 캐시 fallback.
   개별 선수 변환 실패 시 해당 선수만 스킵하고 로그 남김 (전체 파이프라인 중단하지 않음).

3. **컬럼명 하드코딩 금지:** pybaseball 컬럼명은 `extract.py` 내 상수로 관리.
   `BATTING_COLS = {"pa": "PA", "ab": "AB", "hits": "H", ...}` 형태로.

4. **테스트:** API 호출 테스트는 mock 사용. 변환 로직 테스트는 고정된 테스트 데이터 사용.

5. **player_hands 우선순위:**
   - MLB Stats API → Lahman → pybaseball playerid_lookup 순으로 시도
   - 어떤 소스에서도 못 찾으면 "R" (우타) 기본값 + 경고 로그

---

## 부록 A: pybaseball 설치 및 의존성

```bash
pip install pybaseball
pip install MLB-StatsAPI  # statsapi 패키지

# 추가 의존성
pip install pandas numpy pyarrow  # parquet 지원
```

### pybaseball 주의사항

```
1. 첫 호출 시 chadwick register 다운로드 (약 30MB, 1회)
2. FanGraphs 스크래핑이므로 rate limiting 주의 — 연속 호출 사이에 1~2초 sleep
3. Statcast 데이터는 날짜 범위가 필수 (한 번에 전 시즌 불가, 월별 분할 필요)
4. 일부 함수는 시즌 중에만 최신 데이터 반환 (비시즌에는 이전 시즌 데이터)
```

---

## 부록 B: 파이프라인 사용 예시

```python
# 전체 데이터 로드
pipeline = DugoutDataPipeline(season=2024)
data = pipeline.load_all()

# 특정 경기 시뮬레이션
away, home, park = data.get_matchup("NYY", "BOS")
result = simulate_game(away, home, park, data.league, rng=np.random.default_rng(42))
print(result.box_score())

# 1,000회 Monte Carlo
series = simulate_series(away, home, park, data.league, n_simulations=1000)
print(series.summary())
# → {"away_win_pct": 0.534, "avg_away_runs": 4.7, "avg_home_runs": 4.3, ...}

# 전체 팀 순회
for team_id, team in data.teams.items():
    print(f"{team.name}: lineup={[b.name for b in team.lineup]}")
```
