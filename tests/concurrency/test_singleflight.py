""" Test singleflight """

from __future__ import annotations

import threading
import time
from typing import Callable

from cachelab import Cache


def test_singleflight_runs_loader_once_for_concurrent_misses() -> None:
    cache = Cache(capacity=4, shard_count=2)
    calls = 0
    calls_lock = threading.Lock()
    barrier = threading.Barrier(100)
    results: list[str] = []

    def loader() -> str:
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.01)
        return "loaded"

    def read() -> None:
        barrier.wait()
        results.append(cache.get_or_compute("same", loader))

    threads = [threading.Thread(target=read) for _ in range(100)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert calls == 1
    assert results == ["loaded"] * 100


def test_different_keys_load_concurrently() -> None:
    # Single-flight collapses duplicate loads of the SAME key, but distinct keys
    # must still load in parallel. Each loader blocks on a 2-party barrier, so the
    # test only completes if both loaders run at once (a serialized implementation
    # would time out on the barrier and drop a result).
    cache = Cache(capacity=8, shard_count=4)
    barrier = threading.Barrier(2)
    results: dict[str, str] = {}

    def make_loader(key: str) -> Callable[[], str]:
        def loader() -> str:
            barrier.wait(timeout=2)
            return f"v-{key}"

        return loader

    def run(key: str) -> None:
        results[key] = cache.get_or_compute(key, make_loader(key))

    threads = [threading.Thread(target=run, args=(key,)) for key in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results == {"a": "v-a", "b": "v-b"}


def test_loader_failure_does_not_poison_cache() -> None:
    cache = Cache(capacity=4)

    def loader() -> str:
        raise RuntimeError("boom")

    try:
        cache.get_or_compute("bad", loader)
    except RuntimeError:
        pass
    assert cache.contains("bad") is False
