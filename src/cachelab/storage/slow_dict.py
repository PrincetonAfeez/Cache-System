""" Slow dict storage utilities for CacheLab """

from __future__ import annotations

import threading
from typing import Any, Hashable

from cachelab.core.clock import Clock, MonotonicClock


class SlowDictBackend:
    """Artificial slow source-of-truth backend for write mode demos.

    ``clock`` drives only the artificial I/O ``delay`` and defaults to its own
    monotonic clock. Do not pass the owning cache's clock here: a shared
    ``FakeClock`` would advance from inside a backend write and spuriously expire
    cache entries.
    """

    def __init__(self, delay: float = 0.0, clock: Clock | None = None) -> None:
        self.delay = delay
        self.clock = clock or MonotonicClock()
        self._data: dict[Hashable, Any] = {}
        self._lock = threading.Lock()
        self._failures_remaining = 0

    def fail_next(self, count: int = 1) -> None:
        with self._lock:
            self._failures_remaining += count

    def put_value(self, key: Hashable, value: Any) -> None:
        self._maybe_delay_and_fail()
        with self._lock:
            self._data[key] = value

    def delete_value(self, key: Hashable) -> None:
        self._maybe_delay_and_fail()
        with self._lock:
            self._data.pop(key, None)

    def get_value(self, key: Hashable) -> Any:
        self._maybe_delay_and_fail(delay_only=True)
        with self._lock:
            return self._data.get(key)

    def snapshot(self) -> dict[Hashable, Any]:
        with self._lock:
            return dict(self._data)

    def _maybe_delay_and_fail(self, delay_only: bool = False) -> None:
        if self.delay > 0:
            self.clock.sleep(self.delay)
        if delay_only:
            return
        with self._lock:
            if self._failures_remaining > 0:
                self._failures_remaining -= 1
                raise OSError("injected SlowDictBackend failure")
