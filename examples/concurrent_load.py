"""Single-flight: 50 concurrent misses for one key invoke the loader once."""

from __future__ import annotations

import threading
import time

from cachelab import Cache


def main() -> None:
    cache = Cache(capacity=8, shard_count=2)
    calls = 0
    calls_lock = threading.Lock()
    barrier = threading.Barrier(50)
    results: list[str] = []

    def loader() -> str:
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        return "loaded"

    def read() -> None:
        barrier.wait()
        results.append(cache.get_or_compute("same-key", loader))

    threads = [threading.Thread(target=read) for _ in range(50)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    print("loader calls:", calls)
    print("unique results:", set(results))
    print("stats:", cache.stats())


if __name__ == "__main__":
    main()
