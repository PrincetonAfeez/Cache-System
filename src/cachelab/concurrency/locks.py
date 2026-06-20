""" Lock utilities for CacheLab """

from __future__ import annotations

import threading
from types import TracebackType


class MeteredRLock:
    """RLock wrapper that counts contended acquisitions."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._contentions = 0
        self._counter_lock = threading.Lock()

    def acquire(self) -> None:
        if self._lock.acquire(blocking=False):
            return
        with self._counter_lock:
            self._contentions += 1
        self._lock.acquire()

    def release(self) -> None:
        self._lock.release()

    @property
    def contentions(self) -> int:
        with self._counter_lock:
            return self._contentions

    def __enter__(self) -> "MeteredRLock":
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()
