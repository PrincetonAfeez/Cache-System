""" Unsafe wall clock TTL utilities for CacheLab """

from __future__ import annotations

from typing import Any


class AdjustableWallClock:
    def __init__(self, start: float = 100.0) -> None:
        self.now = start


class UnsafeWallClockTTLCache:
    def __init__(self, clock: AdjustableWallClock) -> None:
        self.clock = clock
        self.data: dict[str, tuple[Any, float]] = {}

    def put(self, key: str, value: Any, ttl: float) -> None:
        self.data[key] = (value, self.clock.now + ttl)

    def contains(self, key: str) -> bool:
        item = self.data.get(key)
        if item is None:
            return False
        _, expires_at = item
        return self.clock.now < expires_at


def unsafe_wall_clock_ttl_demo() -> dict[str, bool | float]:
    clock = AdjustableWallClock()
    cache = UnsafeWallClockTTLCache(clock)
    cache.put("session", "value", ttl=10.0)
    clock.now += 11.0
    expired_after_forward = not cache.contains("session")
    clock.now -= 20.0
    incorrectly_alive_after_backward_jump = cache.contains("session")
    return {
        "expired_after_forward": expired_after_forward,
        "incorrectly_alive_after_backward_jump": incorrectly_alive_after_backward_jump,
        "wall_clock_now": clock.now,
    }
