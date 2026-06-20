""" Unsafe singleflight utilities for CacheLab """

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Hashable


class UnsafeGetOrCompute:
    def __init__(self) -> None:
        self.data: dict[Hashable, Any] = {}

    def get_or_compute(self, key: Hashable, loader: Callable[[], Any]) -> Any:
        if key not in self.data:
            self.data[key] = loader()
        return self.data[key]


def unsafe_singleflight_demo(threads: int = 50) -> dict[str, int]:
    cache = UnsafeGetOrCompute()
    calls = 0
    calls_lock = threading.Lock()
    barrier = threading.Barrier(threads)

    def loader() -> str:
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.005)
        return "loaded"

    def read() -> None:
        barrier.wait()
        cache.get_or_compute("same-key", loader)

    workers = [threading.Thread(target=read) for _ in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    return {"threads": threads, "loader_calls": calls}
