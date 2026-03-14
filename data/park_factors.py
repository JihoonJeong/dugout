"""Park factor 추출/관리."""

from __future__ import annotations

import logging

from engine.models import ParkFactors
from .constants import DEFAULT_PARK_FACTORS

logger = logging.getLogger(__name__)


def extract_park_factors(season: int) -> dict[str, ParkFactors]:
    """구장별 park factor 반환.

    V0.1: DEFAULT_PARK_FACTORS 하드코딩 사용.
    향후 FanGraphs Guts! 페이지 스크래핑으로 교체 예정.
    """
    parks = {}
    for park_name, pf_data in DEFAULT_PARK_FACTORS.items():
        parks[park_name] = ParkFactors(
            park_name=park_name,
            pf_1b=float(pf_data["1B"]),
            pf_2b=float(pf_data["2B"]),
            pf_3b=float(pf_data["3B"]),
            pf_hr=float(pf_data["HR"]),
        )
    logger.info("Loaded park factors for %d parks (season=%d)", len(parks), season)
    return parks
