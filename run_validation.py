"""L1~L4 전체 검증 실행 스크립트."""

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

from validation.runner import ValidationRunner
from validation.report import generate_report
from validation.diagnostics import run_diagnostics
from validation.charts import generate_charts

runner = ValidationRunner(season=2024, version="v0.1.1")
result = runner.run(levels=["L1", "L2", "L3", "L4"], l3_max_games=500)

# 리포트 출력
report = generate_report(result)
print(report)

# 차트 생성
charts = generate_charts(result)
if charts:
    print("\n== Generated Charts ==")
    for c in charts:
        print(f"  {c}")

# 진단
diag = run_diagnostics(result)
if diag.issues:
    print("\n== Diagnostic Issues ==")
    for issue in diag.issues:
        print(f"  ! {issue}")

# 버전 비교
from validation.compare import compare_versions
print("\n== Version Comparison ==")
print(compare_versions())
