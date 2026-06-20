""" Clock utilities for CacheLab """

from __future__ import annotations

import threading
import time
from typing import Protocol


class Clock(Protocol):
    def now(self) -> float:
        """Return monotonic seconds."""

    def sleep(self, seconds: float) -> None:
        """Sleep or advance by monotonic seconds."""


class MonotonicClock:
    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


class FakeClock:
    """Thread-safe monotonic test clock.

    sleep() advances the clock instead of blocking, so correctness tests do not
    need real-time waits.
    """

    def __init__(self, start: float = 0.0) -> None:
        self._now = start
        self._lock = threading.Lock()

    def now(self) -> float:
        with self._lock:
            return self._now

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("fake clock cannot move backwards")
        with self._lock:
            self._now += seconds

    def sleep(self, seconds: float) -> None:
        self.advance(max(0.0, seconds))
