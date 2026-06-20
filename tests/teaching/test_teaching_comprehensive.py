""" Test teaching comprehensive """

from __future__ import annotations

from cachelab.teaching import (
    unsafe_race_demo,
    unsafe_singleflight_demo,
    unsafe_wall_clock_ttl_demo,
    unsafe_write_back_resurrection_demo,
)
from cachelab.teaching.unsafe_cache import UnsafeNoLockCache
from cachelab.teaching.unsafe_wall_clock_ttl import AdjustableWallClock, UnsafeWallClockTTLCache


def test_unsafe_no_lock_cache_direct() -> None:
    cache = UnsafeNoLockCache(capacity=2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert len(cache.data) == 2


def test_unsafe_race_demo_reports_oversize() -> None:
    result = unsafe_race_demo(threads=10, capacity=1)
    assert result["final_size"] > result["capacity"]


def test_unsafe_singleflight_demo_reports_duplicate_loads() -> None:
    result = unsafe_singleflight_demo(threads=20)
    assert result["loader_calls"] > 1


def test_unsafe_write_back_resurrection_demo() -> None:
    result = unsafe_write_back_resurrection_demo()
    assert result["resurrected"] is True


def test_unsafe_wall_clock_ttl_direct() -> None:
    clock = AdjustableWallClock()
    cache = UnsafeWallClockTTLCache(clock)
    cache.put("k", "v", ttl=5.0)
    assert cache.contains("k")
    clock.now += 10.0
    assert not cache.contains("k")


def test_unsafe_wall_clock_ttl_demo() -> None:
    result = unsafe_wall_clock_ttl_demo()
    assert result["expired_after_forward"] is True
    assert result["incorrectly_alive_after_backward_jump"] is True
