# Platoon split 소표본 보정 기준 타석 수
PLATOON_MIN_PA = 100

# 극소 표본 회귀 기준 (PA < 이 값이면 리그 평균으로 강하게 회귀)
SMALL_SAMPLE_PA = 50
SMALL_SAMPLE_DIVISOR = 200

# Stage 1 정규화: non-BIP 확률 합 상한 (BIP 최소 5% 보장)
MAX_NON_BIP = 0.95

# 확률 floor (음수/0 방지)
PROB_FLOOR = 0.001

# FO 최소값 (HR 보정 후 음수 방지)
FO_FLOOR = 0.01

# Rate floor (Log5 odds 계산 시 0 방지)
RATE_FLOOR = 0.001

# 확률 합 검증 허용 오차
TOLERANCE = 1e-9

# --- Phase 0-CD: 게임 시뮬레이션 상수 ---

# 선발 투수 교체 기준
STARTER_PITCH_LIMIT = 100
STARTER_INNING_LIMIT = 6.0

# 불펜 투수 교체 기준 (이닝)
RELIEVER_INNING_LIMIT = 1.0

# 최대 이닝 (연장전 상한)
MAX_INNINGS = 20

# Manfred runner 시작 이닝
MANFRED_RUNNER_INNING = 10

# 투구 수 추정: 표준편차, 상한
PITCH_COUNT_STD = 1.0
PITCH_COUNT_MAX = 12
