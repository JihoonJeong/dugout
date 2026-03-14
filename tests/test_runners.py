"""주자 진루 모델 단위 테스트."""

import numpy as np
import pytest

from engine.models import Runner
from engine.runners import resolve_play


def _r(pid: str, base: str) -> Runner:
    return Runner(player_id=pid, name=pid, from_base=base)


class TestHR:
    def test_solo_hr(self):
        runners, runs, outs = resolve_play("HR", {}, 0, "batter", "Batter", np.random.default_rng(0))
        assert runs == 1
        assert outs == 0
        assert runners == {}

    def test_grand_slam(self):
        bases = {"1B": _r("r1", "1B"), "2B": _r("r2", "2B"), "3B": _r("r3", "3B")}
        runners, runs, outs = resolve_play("HR", bases, 0, "batter", "Batter", np.random.default_rng(0))
        assert runs == 4
        assert runners == {}

    def test_2_runners_hr(self):
        bases = {"1B": _r("r1", "1B"), "3B": _r("r3", "3B")}
        runners, runs, outs = resolve_play("HR", bases, 1, "batter", "Batter", np.random.default_rng(0))
        assert runs == 3


class TestTriple:
    def test_bases_empty(self):
        runners, runs, outs = resolve_play("3B", {}, 0, "batter", "Batter", np.random.default_rng(0))
        assert runs == 0
        assert "3B" in runners
        assert runners["3B"].player_id == "batter"

    def test_runners_score(self):
        bases = {"1B": _r("r1", "1B"), "2B": _r("r2", "2B")}
        runners, runs, outs = resolve_play("3B", bases, 0, "batter", "Batter", np.random.default_rng(0))
        assert runs == 2
        assert "3B" in runners


class TestWalkHBP:
    def test_bases_empty(self):
        runners, runs, outs = resolve_play("BB", {}, 0, "batter", "Batter", np.random.default_rng(0))
        assert runs == 0
        assert "1B" in runners
        assert runners["1B"].player_id == "batter"

    def test_force_advance_1b(self):
        """주자 1루에서 BB → 1루, 2루."""
        bases = {"1B": _r("r1", "1B")}
        runners, runs, outs = resolve_play("BB", bases, 0, "batter", "Batter", np.random.default_rng(0))
        assert runs == 0
        assert runners["1B"].player_id == "batter"
        assert runners["2B"].player_id == "r1"

    def test_no_force_13(self):
        """주자 1,3루에서 BB → 1루주자만 포스, 3루 주자 잔류."""
        bases = {"1B": _r("r1", "1B"), "3B": _r("r3", "3B")}
        runners, runs, outs = resolve_play("BB", bases, 0, "batter", "Batter", np.random.default_rng(0))
        assert runs == 0
        assert runners["1B"].player_id == "batter"
        assert runners["2B"].player_id == "r1"
        assert runners["3B"].player_id == "r3"

    def test_bases_loaded_walk(self):
        """만루에서 BB → 밀어내기 1점."""
        bases = {"1B": _r("r1", "1B"), "2B": _r("r2", "2B"), "3B": _r("r3", "3B")}
        runners, runs, outs = resolve_play("BB", bases, 0, "batter", "Batter", np.random.default_rng(0))
        assert runs == 1
        assert runners["1B"].player_id == "batter"
        assert runners["2B"].player_id == "r1"
        assert runners["3B"].player_id == "r2"

    def test_hbp_same_as_walk(self):
        bases = {"1B": _r("r1", "1B")}
        runners, runs, outs = resolve_play("HBP", bases, 0, "batter", "Batter", np.random.default_rng(0))
        assert runs == 0
        assert runners["1B"].player_id == "batter"
        assert runners["2B"].player_id == "r1"


class TestStrikeout:
    def test_k_no_runner_change(self):
        bases = {"2B": _r("r2", "2B")}
        runners, runs, outs = resolve_play("K", bases, 1, "batter", "Batter", np.random.default_rng(0))
        assert runs == 0
        assert outs == 1
        assert "2B" in runners


class TestSingle:
    def test_bases_empty(self):
        runners, runs, outs = resolve_play("1B", {}, 0, "batter", "Batter", np.random.default_rng(0))
        assert runs == 0
        assert outs == 0
        assert "1B" in runners
        assert runners["1B"].player_id == "batter"


class TestDouble:
    def test_bases_empty(self):
        runners, runs, outs = resolve_play("2B", {}, 0, "batter", "Batter", np.random.default_rng(0))
        assert runs == 0
        assert "2B" in runners
        assert runners["2B"].player_id == "batter"


class TestGO:
    def test_no_dp_without_runner_1b(self):
        """1루 주자 없으면 DP 불가."""
        rng = np.random.default_rng(0)
        for _ in range(50):
            runners, runs, outs = resolve_play("GO", {}, 0, "batter", "Batter", rng)
            assert outs == 1  # 항상 단일 아웃

    def test_no_dp_with_2_outs(self):
        """2아웃이면 DP 불가."""
        bases = {"1B": _r("r1", "1B")}
        rng = np.random.default_rng(0)
        for _ in range(50):
            runners, runs, outs = resolve_play("GO", dict(bases), 2, "batter", "Batter", rng)
            assert outs == 1

    def test_dp_possible(self):
        """1루 주자 + 아웃 < 2 → DP 가능."""
        bases = {"1B": _r("r1", "1B")}
        rng = np.random.default_rng(42)
        results = []
        for _ in range(200):
            _, _, outs = resolve_play("GO", dict(bases), 0, "batter", "Batter", rng)
            results.append(outs)
        assert 2 in results  # DP 발생 확인
        assert 1 in results  # 단일 아웃도 확인


class TestFO:
    def test_sf_possible_with_runner_3b(self):
        """3루 주자 + 아웃 < 2 → SF 가능."""
        bases = {"3B": _r("r3", "3B")}
        rng = np.random.default_rng(42)
        scored = False
        for _ in range(100):
            _, runs, outs = resolve_play("FO", dict(bases), 0, "batter", "Batter", rng)
            assert outs == 1
            if runs > 0:
                scored = True
        assert scored

    def test_no_sf_with_2_outs(self):
        """2아웃 FO → SF 불가."""
        bases = {"3B": _r("r3", "3B")}
        rng = np.random.default_rng(42)
        for _ in range(50):
            _, runs, outs = resolve_play("FO", dict(bases), 2, "batter", "Batter", rng)
            assert runs == 0
